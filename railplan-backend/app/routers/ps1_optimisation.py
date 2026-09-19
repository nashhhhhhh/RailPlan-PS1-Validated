"""Terminal-only optimiser storage with no transaction held across solving."""
import logging
import os
import json
import hashlib
from datetime import datetime, timezone
from time import monotonic
from typing import Annotated, Literal
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy import text
from sqlalchemy.orm import Session
from app import ps1_optimisation_models, repository
from app.database import engine
from app.dependencies import Actor, DB, Limit, Offset, role, identity
from app.ps1_validation.persistence import get_instance
from app.ps1_validation.submission import fingerprint
from app.ps1 import InstanceError, parse_instance
from app.ps1_optimisation.contracts import (OptimiseInput, OptimiseResult, ScenarioAPreviewInput, ScenarioBPreviewInput, ScenarioBOptimiseInput, ScenarioCPreviewInput, ScenarioCOptimiseInput)
from app.ps1_optimisation.saved_contracts import SavedOptimiseInput, SavedOptimiseResult, OptimisationPage, OptimisationDetail, OptimisationArtifacts, OptimisationJob, OptimisationJobAccepted
from app.ps1_optimisation.preprocessing import InputError
from app.ps1_optimisation.service import optimise, optimise_scenario_b, optimise_scenario_c
from app.ps1_optimisation import persistence as store
from app.ps1_optimisation import jobs as job_runner

router=APIRouter(prefix='/api/ps1',tags=['PS1 optimisation'])
logger=logging.getLogger(__name__)

@router.post('/optimise/scenario-a/preview',response_model=OptimiseResult)
def scenario_a_preview(payload:ScenarioAPreviewInput):
    """Run Scenario A without authentication or PostgreSQL and retain rich validation."""
    try:
        dataset=parse_instance(payload.instance_files)
        options=OptimiseInput.model_validate(payload.model_dump(exclude={'instance_files'}))
        return optimise(dataset,options)
    except (InstanceError,InputError,UnicodeEncodeError) as exc:
        raise HTTPException(422,str(exc)) from exc

@router.post('/optimise/scenario-b/preview',response_model=OptimiseResult)
def scenario_b_preview(payload:ScenarioBPreviewInput):
    """Run Scenario B without authentication or PostgreSQL."""
    try:
        dataset=parse_instance(payload.instance_files)
        options=ScenarioBOptimiseInput.model_validate(payload.model_dump(exclude={'instance_files'}))
        return optimise_scenario_b(dataset,options)
    except (InstanceError,InputError,UnicodeEncodeError) as exc:
        raise HTTPException(422,str(exc)) from exc

@router.post('/optimise/scenario-c/preview',response_model=OptimiseResult)
def scenario_c_preview(payload:ScenarioCPreviewInput):
    """Run Scenario C without authentication or PostgreSQL."""
    try:
        dataset=parse_instance(payload.instance_files)
        options=ScenarioCOptimiseInput.model_validate(payload.model_dump(exclude={'instance_files'}))
        return optimise_scenario_c(dataset,options)
    except (InstanceError,InputError,UnicodeEncodeError) as exc:
        raise HTTPException(422,str(exc)) from exc

def optimisation_session_factory():
    """Dedicated boundary: never commit inside the shared DB dependency's begin block."""
    if not os.environ.get('DATABASE_URL'):raise HTTPException(503,'DATABASE_URL is not configured')
    # The post-lock key recheck must see a concurrently committed row.
    return lambda:Session(engine().execution_options(isolation_level='READ COMMITTED'))

def _worker_context(db,actor,correlation_id):
    db.execute(text("""SELECT set_config('railplan.actor_id',:actor,true),
        set_config('railplan.source','worker',true),set_config('railplan.correlation_id',:correlation,true)"""),
        {'actor':str(actor['id']),'correlation':str(correlation_id)})

def _job_record(db,actor,job_id,lock=False):
    suffix=' FOR UPDATE' if lock else ''
    row=db.execute(text('''SELECT * FROM railplan.ps1_optimisation_jobs
        WHERE id=:id AND operator_id=:operator'''+suffix),{'id':job_id,'operator':actor['operator_id']}).mappings().one_or_none()
    if row is None:raise HTTPException(404,'PS1 optimisation job not found')
    return dict(row)

def _job_view(row):
    """Expose immutable request metadata and linked immutable terminal evidence."""
    item=dict(row);snapshot=item.get('request_snapshot') or {}
    capture=snapshot.get('capture',snapshot)
    options=capture.get('option_snapshot',capture.get('solver_options',snapshot.get('request',snapshot)))
    item.update({
        'solver_seed':capture.get('solver_seed',options.get('random_seed',0)),
        'time_limit_seconds':capture.get('time_limit_seconds',options.get('time_limit_seconds',20)),
        'deterministic_time_limit':capture.get('deterministic_time_limit',options.get('deterministic_time_limit',10)),
        'option_snapshot':options,
        'validator_version':capture.get('validator_version','legacy-not-captured'),
        'policy_version':capture.get('policy_version','legacy-not-captured'),
        'solver_status':item.get('solver_status'),
        'objective_components':item.get('objective_components'),
        'best_objective':item.get('best_objective'),
        'best_bound':item.get('best_bound'),
        'validation_result':item.get('validation_result'),
        'diagnostics':item.get('diagnostics') or [],
        'artifact_eligible':bool(item.get('artifact_eligible',False)),
    })
    return item

_JOB_SELECT='''SELECT j.*,
    r.solver_status,r.result_snapshot->'objective_components' AS objective_components,
    r.objective_score::text AS best_objective,r.primary_objective_bound::text AS best_bound,
    r.validation_snapshot AS validation_result,r.diagnostics,
    COALESCE(r.publishable,false) AS artifact_eligible
    FROM railplan.ps1_optimisation_jobs j
    LEFT JOIN railplan.ps1_optimisation_runs r
      ON r.id=j.run_id AND r.instance_id=j.instance_id AND r.operator_id=j.operator_id'''

def _job(db,actor,job_id):
    row=db.execute(text(_JOB_SELECT+''' WHERE j.id=:id AND j.operator_id=:operator'''),
        {'id':job_id,'operator':actor['operator_id']}).mappings().one_or_none()
    if row is None:raise HTTPException(404,'PS1 optimisation job not found')
    return _job_view(row)

def _job_update(db,job_id,*,status,progress,stage,run_id=None,diagnostic=None,cancel_requested=None):
    return dict(db.execute(text('''UPDATE railplan.ps1_optimisation_jobs SET status=:status,progress=:progress,stage=:stage,
        run_id=COALESCE(:run_id,run_id),diagnostic=COALESCE(CAST(:diagnostic AS jsonb),diagnostic),
        cancel_requested=COALESCE(:cancel_requested,cancel_requested)
        WHERE id=:id RETURNING *'''),{'id':job_id,'status':status,'progress':progress,'stage':stage,'run_id':run_id,
        'diagnostic':json.dumps(diagnostic) if diagnostic is not None else None,'cancel_requested':cancel_requested}).mappings().one())

def _recover_abandoned(db,actor):
    """Seal jobs absent from this single process registry as restart evidence."""
    rows=db.execute(text('''SELECT id FROM railplan.ps1_optimisation_jobs
        WHERE operator_id=:operator AND status IN ('QUEUED','RUNNING','CANCELLATION_REQUESTED')'''),
        {'operator':actor['operator_id']}).scalars().all()
    for job_id in rows:
        if not job_runner.active(job_id):
            db.execute(text('''UPDATE railplan.ps1_optimisation_jobs
                SET status='FAILED',stage='abandoned_after_process_restart',
                    started_at=COALESCE(started_at,clock_timestamp()),diagnostic=CAST(:diagnostic AS jsonb)
                WHERE id=:id AND status IN ('QUEUED','RUNNING','CANCELLATION_REQUESTED')'''),
                {'id':job_id,'diagnostic':json.dumps({'code':'abandoned_after_process_restart',
                    'message':'The process-local executor ended before this durable job reached a terminal state.'})})

def _execute_job(factory,job_id,actor,instance,payload,configuration,digest,correlation_id,cancel_event):
    """Compute outside transactions; persist terminal evidence in short transactions."""
    try:
        with factory() as db:
            with db.begin():
                _worker_context(db,actor,correlation_id)
                current=_job_record(db,actor,job_id,lock=True)
                if current['status'] in ('SUCCEEDED','FAILED','CANCELLED'):return
                if current['cancel_requested'] or cancel_event.is_set():
                    _job_update(db,job_id,status='CANCELLED',progress=current['progress'],stage='cancelled',cancel_requested=True)
                    return
                _job_update(db,job_id,status='RUNNING',progress=10,stage='building_model')
        started=datetime.now(timezone.utc);options=store.resolve_options_snapshot(configuration)
        scenario=configuration['scenario']
        result={'A':optimise,'B':optimise_scenario_b,'C':optimise_scenario_c}[scenario](instance['dataset'],options)
        records=store.schedule_records(instance,options,result,scenario)
        completed=datetime.now(timezone.utc)
        with factory() as db:
            with db.begin():
                _worker_context(db,actor,correlation_id)
                current=_job_record(db,actor,job_id,lock=True)
                if current['status'] in ('SUCCEEDED','FAILED','CANCELLED'):return
                if current['cancel_requested'] or cancel_event.is_set():
                    _job_update(db,job_id,status='CANCELLED',progress=max(80,current['progress']),stage='cancelled',cancel_requested=True,
                        diagnostic={'code':'cancelled_after_solver_boundary','candidate_published':False})
                    return
                # Recheck source ownership and creator activity at the persistence boundary.
                active=db.execute(text('''SELECT 1 FROM railplan.users u JOIN railplan.departments d ON d.id=u.department_id
                    WHERE u.id=:user AND u.active AND d.operator_id=:operator'''),{'user':actor['id'],'operator':actor['operator_id']}).scalar_one_or_none()
                if active is None:raise RuntimeError('Optimisation creator is no longer active in the source operator')
                get_instance(db,actor,instance['id'])
                _job_update(db,job_id,status='RUNNING',progress=85,stage='persisting_terminal_evidence')
                # The job table owns async idempotency. Do not collide with the
                # legacy scenario-agnostic synchronous run-key table.
                run_payload=payload.model_copy(update={'idempotency_key':None})
                saved=store.persist(db,actor,instance,run_payload,configuration,digest,result,records,started,completed,scenario)
                _job_update(db,job_id,status='SUCCEEDED',progress=100,stage=f'completed:{result.solver_status.lower()}',run_id=saved.run_id)
    except Exception as exc:
        logger.exception('Asynchronous PS1 job failed (%s)',correlation_id)
        try:
            with factory() as db:
                with db.begin():
                    _worker_context(db,actor,correlation_id)
                    current=_job_record(db,actor,job_id,lock=True)
                    if current['status'] not in ('SUCCEEDED','FAILED','CANCELLED'):
                        status='CANCELLED' if current['cancel_requested'] or cancel_event.is_set() else 'FAILED'
                        _job_update(db,job_id,status=status,progress=current['progress'],stage=status.lower(),
                            diagnostic={'code':'job_execution_failed','error_type':type(exc).__name__,'correlation_id':str(correlation_id)})
        except Exception:logger.exception('Could not store asynchronous PS1 job failure (%s)',correlation_id)

@router.post('/instances/{instance_id}/optimise/scenario-a',response_model=SavedOptimiseResult)
def scenario_a(instance_id:UUID,payload:SavedOptimiseInput,request:Request,
               factory=Depends(optimisation_session_factory),
               x_demo_user_id:Annotated[UUID|None,Header()]=None):
    return _saved_scenario(instance_id,payload,request,factory,x_demo_user_id,'A')

@router.post('/instances/{instance_id}/optimise/scenario-b',response_model=SavedOptimiseResult)
def scenario_b(instance_id:UUID,payload:SavedOptimiseInput,request:Request,
               factory=Depends(optimisation_session_factory),
               x_demo_user_id:Annotated[UUID|None,Header()]=None):
    return _saved_scenario(instance_id,payload,request,factory,x_demo_user_id,'B')

@router.post('/instances/{instance_id}/optimise/scenario-c',response_model=SavedOptimiseResult)
def scenario_c(instance_id:UUID,payload:SavedOptimiseInput,request:Request,
               factory=Depends(optimisation_session_factory),
               x_demo_user_id:Annotated[UUID|None,Header()]=None):
    return _saved_scenario(instance_id,payload,request,factory,x_demo_user_id,'C')

def _saved_scenario(instance_id,payload,request,factory,x_demo_user_id,scenario):
    try:
        with factory() as db:
            with db.begin():
                actor=identity(request,db,x_demo_user_id)
                role(actor,'planner','administrator')
                instance=get_instance(db,actor,instance_id)
                options=(store.resolve(db,actor,instance,payload) if scenario=='A'
                    else store.resolve(db,actor,instance,payload,scenario))
                configuration=(store.effective_configuration(instance,options,payload.baseline_run_id) if scenario=='A'
                    else store.effective_configuration(instance,options,payload.baseline_run_id,scenario))
                digest=fingerprint(configuration)
                previous=store.existing_key(db,actor,instance_id,payload.idempotency_key,digest)
                reused=store.response(previous,False) if previous else None
        if reused is not None:return reused
        started=datetime.now(timezone.utc); clock=monotonic(); computed=None
        try:
            computed={'A':optimise,'B':optimise_scenario_b,'C':optimise_scenario_c}[scenario](instance['dataset'],options)
            result=computed
            records=(store.schedule_records(instance,options,result) if scenario=='A'
                else store.schedule_records(instance,options,result,scenario))
        except InputError:
            raise
        except Exception as exc:
            logger.exception('PS1 optimisation computation failed (%s)',request.state.correlation_id)
            result=OptimiseResult(scenario=scenario,solver_status='ERROR',solve_time_seconds=monotonic()-clock,
                failed_candidate={'diagnostic_only':True,'result_snapshot':computed.model_dump(mode='json')} if computed is not None else None,
                settings=configuration,diagnostics=[{'code':'handled_solver_error','error_type':type(exc).__name__,
                    'message':'Optimisation computation failed; use the correlation ID for server diagnostics.',
                    'correlation_id':request.state.correlation_id}])
            records={'accesses':[],'occupancies':[],'contract_results':[]}
        completed=datetime.now(timezone.utc)
        with factory() as db:
            with db.begin():
                final_actor=identity(request,db,x_demo_user_id)
                role(final_actor,'planner','administrator')
                get_instance(db,final_actor,instance_id)
                if final_actor['operator_id']!=actor['operator_id']:
                    raise HTTPException(404,'PS1 instance not found')
                saved=(store.persist(db,final_actor,instance,payload,configuration,digest,result,records,started,completed) if scenario=='A'
                    else store.persist(db,final_actor,instance,payload,configuration,digest,result,records,started,completed,scenario))
        return saved
    except InputError as exc:raise HTTPException(422,str(exc)) from exc

@router.post('/instances/{instance_id}/optimise/scenario-a/jobs',response_model=OptimisationJobAccepted,status_code=202)
def scenario_a_job(instance_id:UUID,payload:SavedOptimiseInput,request:Request,
                   factory=Depends(optimisation_session_factory),
                   x_demo_user_id:Annotated[UUID|None,Header()]=None):
    return _start_job(instance_id,payload,request,factory,x_demo_user_id,'A')

@router.post('/instances/{instance_id}/optimise/scenario-b/jobs',response_model=OptimisationJobAccepted,status_code=202)
def scenario_b_job(instance_id:UUID,payload:SavedOptimiseInput,request:Request,
                   factory=Depends(optimisation_session_factory),
                   x_demo_user_id:Annotated[UUID|None,Header()]=None):
    return _start_job(instance_id,payload,request,factory,x_demo_user_id,'B')

@router.post('/instances/{instance_id}/optimise/scenario-c/jobs',response_model=OptimisationJobAccepted,status_code=202)
def scenario_c_job(instance_id:UUID,payload:SavedOptimiseInput,request:Request,
                   factory=Depends(optimisation_session_factory),
                   x_demo_user_id:Annotated[UUID|None,Header()]=None):
    return _start_job(instance_id,payload,request,factory,x_demo_user_id,'C')

def _idempotency_token(scenario,key):
    if key is None:return None
    return scenario.lower()+':'+hashlib.sha256(key.encode('utf-8')).hexdigest()

def _job_capture(payload,configuration):
    options=configuration['solver_options']
    return {'schema_version':2,'request':payload.model_dump(mode='json',exclude_unset=True),'capture':{
        'solver_seed':options['random_seed'],'time_limit_seconds':options['time_limit_seconds'],
        'deterministic_time_limit':options['deterministic_time_limit'],'option_snapshot':options,
        'validator_version':configuration['validator_version'],'policy_version':configuration['policy_version'],
        'optimiser_version':configuration['optimiser_version'],'objective_policy':configuration['objective_policy'],
        'dataset_fingerprint':configuration['dataset_fingerprint']}}

def _start_job(instance_id,payload,request,factory,x_demo_user_id,scenario):
    """Queue one scenario through the shared durable lifecycle."""
    reserved=None
    try:
        with factory() as db:
            with db.begin():
                actor=identity(request,db,x_demo_user_id);role(actor,'planner','administrator')
                _recover_abandoned(db,actor)
                instance=get_instance(db,actor,instance_id)
                options=store.resolve(db,actor,instance,payload,scenario)
                configuration=store.effective_configuration(instance,options,payload.baseline_run_id,scenario)
                digest=fingerprint(configuration)
                token=_idempotency_token(scenario,payload.idempotency_key)
                if payload.idempotency_key:
                    db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:scope,0))'),
                        {'scope':f'ps1-opt-job/{actor["operator_id"]}/{instance_id}/{scenario}/{payload.idempotency_key}'})
                    existing=db.execute(text('''SELECT * FROM railplan.ps1_optimisation_jobs
                        WHERE operator_id=:operator AND instance_id=:instance AND scenario=:scenario
                          AND (idempotency_key=:token OR (:legacy IS NOT NULL AND idempotency_key=:legacy))'''),
                        {'operator':actor['operator_id'],'instance':instance_id,'scenario':scenario,
                         'token':token,'legacy':payload.idempotency_key if scenario=='A' else None}).mappings().one_or_none()
                    if existing:
                        if existing['input_fingerprint']!=digest:raise HTTPException(409,'Idempotency key already used for different optimiser job input')
                        return {'job':_job(db,actor,existing['id']),'created':False,'reused':True}
                job_id=uuid4();reserved=job_id;job_runner.reserve(job_id)
                row=db.execute(text('''INSERT INTO railplan.ps1_optimisation_jobs
                    (id,instance_id,operator_id,created_by,scenario,status,progress,stage,idempotency_key,input_fingerprint,request_snapshot)
                    VALUES(:id,:instance,:operator,:creator,:scenario,'QUEUED',0,'queued',:key,:fingerprint,CAST(:request AS jsonb)) RETURNING *'''),
                    {'id':job_id,'instance':instance_id,'operator':actor['operator_id'],'creator':actor['id'],
                     'scenario':scenario,'key':token,'fingerprint':digest,
                     'request':json.dumps(_job_capture(payload,configuration))}).mappings().one()
        correlation_id=UUID(str(request.state.correlation_id))
        job_runner.launch(job_id,lambda event:_execute_job(factory,job_id,actor,instance,payload,configuration,digest,correlation_id,event))
        return {'job':_job_view(row),'created':True,'reused':False}
    except InputError as exc:
        if reserved is not None:job_runner.release(reserved)
        raise HTTPException(422,str(exc)) from exc
    except Exception:
        if reserved is not None:job_runner.release(reserved)
        raise

@router.get('/optimisation-jobs/{job_id}',response_model=OptimisationJob)
def optimisation_job(job_id:UUID,db:DB,actor:Actor):
    _recover_abandoned(db,actor)
    return _job(db,actor,job_id)

@router.get('/instances/{instance_id}/optimisation-jobs',response_model=OptimisationPage)
def optimisation_jobs(instance_id:UUID,db:DB,actor:Actor,limit:Limit=50,offset:Offset=0,
                      scenario:Literal['A','B','C']|None=Query(default=None)):
    _recover_abandoned(db,actor)
    get_instance(db,actor,instance_id)
    where=''' WHERE j.instance_id=:instance AND j.operator_id=:op
        AND (CAST(:scenario AS text) IS NULL OR j.scenario=:scenario)'''
    params={'instance':instance_id,'op':actor['operator_id'],'scenario':scenario}
    total=db.execute(text('SELECT count(*) FROM railplan.ps1_optimisation_jobs j'+where),params).scalar_one()
    rows=db.execute(text(_JOB_SELECT+where+''' ORDER BY j.created_at DESC,j.id DESC LIMIT :limit OFFSET :offset'''),
        {**params,'limit':limit,'offset':offset}).mappings()
    return {'items':[_job_view(row) for row in rows],'total':total,'limit':limit,'offset':offset}

@router.post('/optimisation-jobs/{job_id}/cancel',response_model=OptimisationJob)
def cancel_optimisation_job(job_id:UUID,db:DB,actor:Actor):
    role(actor,'planner','administrator')
    _recover_abandoned(db,actor)
    row=_job_record(db,actor,job_id,lock=True)
    if row['status'] in ('SUCCEEDED','FAILED','CANCELLED'):
        raise HTTPException(409,'Terminal optimisation jobs cannot be cancelled')
    if row['status']=='QUEUED':
        # The existing schema requires a start timestamp for every terminal row.
        _job_update(db,job_id,status='RUNNING',progress=row['progress'],stage='cancellation_requested',cancel_requested=True,
            diagnostic={'code':'operator_cancellation_requested'})
        _job_update(db,job_id,status='CANCELLED',progress=row['progress'],stage='cancelled',cancel_requested=True)
    else:
        _job_update(db,job_id,status='RUNNING',progress=row['progress'],stage='cancellation_requested',cancel_requested=True,
            diagnostic={'code':'operator_cancellation_requested'})
    job_runner.request_cancel(job_id)
    return _job(db,actor,job_id)

@router.get('/instances/{instance_id}/optimisations',response_model=OptimisationPage)
def history(instance_id:UUID,db:DB,actor:Actor,limit:Limit=50,offset:Offset=0,
            scenario:Literal['A','B','C']|None=Query(default=None)):
    get_instance(db,actor,instance_id)
    return repository.page(db,'''SELECT id,instance_id,baseline_run_id,scenario,solver_status,terminal_outcome,
        primary_optimal,lexicographic_complete,physical_validation_complete,publishable,
        objective_score::text AS objective_score,primary_objective_bound::text AS primary_objective_bound,
        primary_objective_gap::text AS primary_objective_gap,solve_duration_seconds,created_at
        FROM railplan.ps1_optimisation_runs WHERE instance_id=:instance AND operator_id=:op
        AND (CAST(:scenario AS text) IS NULL OR scenario=:scenario)
        ORDER BY created_at DESC,id DESC''',{'instance':instance_id,'op':actor['operator_id']},limit,offset)

@router.get('/optimisations/{run_id}',response_model=OptimisationDetail)
def detail(run_id:UUID,db:DB,actor:Actor):
    run=store.get_run(db,actor,run_id)
    contracts=repository.rows(db,'''SELECT contract_number,simulated_completion_date,overrun_days,
        weighted_overrun::text AS weighted_overrun FROM railplan.ps1_optimisation_contract_results
        WHERE run_id=:id AND operator_id=:op ORDER BY contract_number''',id=run_id,op=actor['operator_id'])
    result=run.pop('result_snapshot');validation=run.pop('validation_snapshot');diagnostics=run.pop('diagnostics')
    for key in ('schedule_snapshot','accepted_csvs','creation_txid'):run.pop(key)
    for key in ('objective_score','primary_objective_bound','primary_objective_gap'):
        if run[key] is not None:run[key]=str(run[key])
    return {'run':run,'result':result,'validation':validation,'diagnostics':diagnostics,'contract_results':contracts}

@router.get('/optimisations/{run_id}/accesses',response_model=OptimisationPage)
def accesses(run_id:UUID,db:DB,actor:Actor,limit:Limit=50,offset:Offset=0,
             week:int|None=Query(default=None,ge=1,le=520),activity_id:str|None=Query(default=None,min_length=1,max_length=128)):
    store.get_run(db,actor,run_id)
    return repository.page(db,'''SELECT activity_id,access_seq,week,physical_night,access_night,eclo,locked,baseline_week,baseline_physical_night
        FROM railplan.ps1_optimisation_accesses WHERE run_id=:id AND operator_id=:op
        AND (CAST(:week AS integer) IS NULL OR week=:week) AND (CAST(:activity AS text) IS NULL OR activity_id=:activity)
        ORDER BY week,activity_id,access_seq''',{'id':run_id,'op':actor['operator_id'],'week':week,'activity':activity_id},limit,offset)

@router.get('/optimisations/{run_id}/occupancies',response_model=OptimisationPage)
def occupancies(run_id:UUID,db:DB,actor:Actor,limit:Limit=50,offset:Offset=0,
                week:int|None=Query(default=None,ge=1,le=520),activity_id:str|None=Query(default=None,min_length=1,max_length=128),
                location_id:str|None=Query(default=None,min_length=1,max_length=128)):
    store.get_run(db,actor,run_id)
    return repository.page(db,'''SELECT activity_id,week,location_id,co_share_group FROM railplan.ps1_optimisation_occupancies
        WHERE run_id=:id AND operator_id=:op AND (CAST(:week AS integer) IS NULL OR week=:week)
        AND (CAST(:activity AS text) IS NULL OR activity_id=:activity) AND (CAST(:location AS text) IS NULL OR location_id=:location)
        ORDER BY week,location_id,activity_id''',{'id':run_id,'op':actor['operator_id'],'week':week,'activity':activity_id,'location':location_id},limit,offset)

@router.get('/optimisations/{run_id}/artifacts',response_model=OptimisationArtifacts)
def artifacts(run_id:UUID,db:DB,actor:Actor):
    run=store.get_run(db,actor,run_id)
    if not run['publishable'] or run['accepted_csvs'] is None:raise HTTPException(409,'Run has no internally accepted submission artifacts')
    return {'run_id':run_id,'files':run['accepted_csvs'],'physical_validation_complete':run['physical_validation_complete'],
        'judge_validation':'not_run','score_verification':'internal_only'}
