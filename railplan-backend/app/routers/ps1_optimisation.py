"""Terminal-only optimiser storage with no transaction held across solving."""
import logging
import os
import json
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

def _job(db,actor,job_id):
    row=db.execute(text('''SELECT * FROM railplan.ps1_optimisation_jobs
        WHERE id=:id AND operator_id=:operator'''),{'id':job_id,'operator':actor['operator_id']}).mappings().one_or_none()
    if row is None:raise HTTPException(404,'PS1 optimisation job not found')
    return dict(row)

def _job_update(db,job_id,*,status,progress,stage,run_id=None,diagnostic=None,cancel_requested=None):
    return dict(db.execute(text('''UPDATE railplan.ps1_optimisation_jobs SET status=:status,progress=:progress,stage=:stage,
        run_id=COALESCE(:run_id,run_id),diagnostic=CAST(:diagnostic AS jsonb),
        cancel_requested=COALESCE(:cancel_requested,cancel_requested)
        WHERE id=:id RETURNING *'''),{'id':job_id,'status':status,'progress':progress,'stage':stage,'run_id':run_id,
        'diagnostic':json.dumps(diagnostic) if diagnostic is not None else None,'cancel_requested':cancel_requested}).mappings().one())

def _execute_job(factory,job_id,actor,instance,payload,configuration,digest,correlation_id,cancel_event):
    """Compute outside transactions; persist terminal evidence in short transactions."""
    try:
        with factory() as db:
            with db.begin():
                _worker_context(db,actor,correlation_id)
                current=_job(db,actor,job_id)
                if current['cancel_requested'] or cancel_event.is_set():
                    _job_update(db,job_id,status='CANCELLED',progress=current['progress'],stage='cancelled',cancel_requested=True)
                    return
                _job_update(db,job_id,status='RUNNING',progress=10,stage='building_model')
        started=datetime.now(timezone.utc);clock=monotonic();computed=None
        try:
            computed=optimise(instance['dataset'],store.resolve_options_snapshot(configuration))
            result=computed
            records=store.schedule_records(instance,store.resolve_options_snapshot(configuration),result)
        except Exception as exc:
            logger.exception('Asynchronous PS1 optimisation computation failed (%s)',correlation_id)
            result=OptimiseResult(solver_status='ERROR',solve_time_seconds=monotonic()-clock,
                failed_candidate={'diagnostic_only':True,'result_snapshot':computed.model_dump(mode='json')} if computed is not None else None,
                settings=configuration,diagnostics=[{'code':'handled_solver_error','error_type':type(exc).__name__,
                    'message':'Optimisation computation failed; use the correlation ID for server diagnostics.','correlation_id':str(correlation_id)}])
            records={'accesses':[],'occupancies':[],'contract_results':[]}
        completed=datetime.now(timezone.utc)
        with factory() as db:
            with db.begin():
                _worker_context(db,actor,correlation_id)
                current=_job(db,actor,job_id)
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
                saved=store.persist(db,actor,instance,payload,configuration,digest,result,records,started,completed)
                _job_update(db,job_id,status='SUCCEEDED',progress=100,stage=f'completed:{result.solver_status.lower()}',run_id=saved.run_id)
    except Exception as exc:
        logger.exception('Asynchronous PS1 job failed (%s)',correlation_id)
        try:
            with factory() as db:
                with db.begin():
                    _worker_context(db,actor,correlation_id)
                    current=_job(db,actor,job_id)
                    if current['status'] not in ('SUCCEEDED','FAILED','CANCELLED'):
                        _job_update(db,job_id,status='FAILED',progress=current['progress'],stage='failed',
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
    """Queue a durable Scenario A job; polling and cancellation are operator scoped."""
    try:
        with factory() as db:
            with db.begin():
                actor=identity(request,db,x_demo_user_id);role(actor,'planner','administrator')
                instance=get_instance(db,actor,instance_id)
                options=store.resolve(db,actor,instance,payload)
                configuration=store.effective_configuration(instance,options,payload.baseline_run_id)
                digest=fingerprint(configuration)
                if payload.idempotency_key:
                    db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:scope,0))'),
                        {'scope':f'ps1-opt-job/{actor["operator_id"]}/{instance_id}/{payload.idempotency_key}'})
                    existing=db.execute(text('''SELECT * FROM railplan.ps1_optimisation_jobs
                        WHERE operator_id=:operator AND instance_id=:instance AND idempotency_key=:key'''),
                        {'operator':actor['operator_id'],'instance':instance_id,'key':payload.idempotency_key}).mappings().one_or_none()
                    if existing:
                        if existing['input_fingerprint']!=digest:raise HTTPException(409,'Idempotency key already used for different optimiser job input')
                        return {'job':dict(existing),'created':False,'reused':True}
                    completed_run=store.existing_key(db,actor,instance_id,payload.idempotency_key,digest)
                else:completed_run=None
                job_id=uuid4();now=datetime.now(timezone.utc)
                if completed_run:
                    saved=store.response(completed_run,False)
                    row=db.execute(text('''INSERT INTO railplan.ps1_optimisation_jobs
                        (id,instance_id,operator_id,created_by,scenario,status,progress,stage,idempotency_key,input_fingerprint,
                         request_snapshot,cancel_requested,run_id,created_at,started_at,completed_at,updated_at)
                        VALUES(:id,:instance,:operator,:creator,'A','SUCCEEDED',100,:stage,:key,:fingerprint,
                         CAST(:request AS jsonb),false,:run,:now,:now,:now,:now) RETURNING *'''),
                        {'id':job_id,'instance':instance_id,'operator':actor['operator_id'],'creator':actor['id'],
                         'stage':f'completed:{saved.solver_status.lower()}','key':payload.idempotency_key,'fingerprint':digest,
                         'request':json.dumps(payload.model_dump(mode='json',exclude_unset=True)),'run':saved.run_id,'now':now}).mappings().one()
                    return {'job':dict(row),'created':True,'reused':True}
                row=db.execute(text('''INSERT INTO railplan.ps1_optimisation_jobs
                    (id,instance_id,operator_id,created_by,scenario,status,progress,stage,idempotency_key,input_fingerprint,request_snapshot)
                    VALUES(:id,:instance,:operator,:creator,'A','QUEUED',0,'queued',:key,:fingerprint,CAST(:request AS jsonb)) RETURNING *'''),
                    {'id':job_id,'instance':instance_id,'operator':actor['operator_id'],'creator':actor['id'],
                     'key':payload.idempotency_key,'fingerprint':digest,'request':json.dumps(payload.model_dump(mode='json',exclude_unset=True))}).mappings().one()
        correlation_id=UUID(request.state.correlation_id)
        job_runner.launch(job_id,lambda event:_execute_job(factory,job_id,actor,instance,payload,configuration,digest,correlation_id,event))
        return {'job':dict(row),'created':True,'reused':False}
    except InputError as exc:raise HTTPException(422,str(exc)) from exc

@router.get('/optimisation-jobs/{job_id}',response_model=OptimisationJob)
def optimisation_job(job_id:UUID,db:DB,actor:Actor):
    return _job(db,actor,job_id)

@router.get('/instances/{instance_id}/optimisation-jobs',response_model=OptimisationPage)
def optimisation_jobs(instance_id:UUID,db:DB,actor:Actor,limit:Limit=50,offset:Offset=0):
    get_instance(db,actor,instance_id)
    return repository.page(db,'''SELECT id,instance_id,scenario,status,progress,stage,cancel_requested,run_id,diagnostic,
        created_at,started_at,completed_at,updated_at FROM railplan.ps1_optimisation_jobs
        WHERE instance_id=:instance AND operator_id=:op ORDER BY created_at DESC,id DESC''',
        {'instance':instance_id,'op':actor['operator_id'],'scenario':scenario},limit,offset)

@router.post('/optimisation-jobs/{job_id}/cancel',response_model=OptimisationJob)
def cancel_optimisation_job(job_id:UUID,db:DB,actor:Actor):
    role(actor,'planner','administrator')
    row=_job(db,actor,job_id)
    if row['status'] in ('SUCCEEDED','FAILED','CANCELLED'):return row
    target='CANCELLED' if row['status']=='QUEUED' and not job_runner.active(job_id) else 'CANCELLATION_REQUESTED'
    updated=_job_update(db,job_id,status=target,progress=row['progress'],stage='cancellation_requested',cancel_requested=True,
        diagnostic={'code':'operator_cancellation_requested'})
    job_runner.request_cancel(job_id)
    return updated

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
