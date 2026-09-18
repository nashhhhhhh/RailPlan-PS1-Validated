"""Terminal-only optimiser storage with no transaction held across solving."""
import logging
import os
from datetime import datetime, timezone
from time import monotonic
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy.orm import Session
from app import ps1_optimisation_models, repository
from app.database import engine
from app.dependencies import Actor, DB, Limit, Offset, role, identity
from app.ps1_validation.persistence import get_instance
from app.ps1_validation.submission import fingerprint
from app.ps1_optimisation.contracts import OptimiseResult
from app.ps1_optimisation.saved_contracts import SavedOptimiseInput, SavedOptimiseResult, OptimisationPage, OptimisationDetail, OptimisationArtifacts
from app.ps1_optimisation.preprocessing import InputError
from app.ps1_optimisation.service import optimise
from app.ps1_optimisation import persistence as store

router=APIRouter(prefix='/api/ps1',tags=['PS1 Scenario A optimisation'])
logger=logging.getLogger(__name__)

def optimisation_session_factory():
    """Dedicated boundary: never commit inside the shared DB dependency's begin block."""
    if not os.environ.get('DATABASE_URL'):raise HTTPException(503,'DATABASE_URL is not configured')
    # The post-lock key recheck must see a concurrently committed row.
    return lambda:Session(engine().execution_options(isolation_level='READ COMMITTED'))

@router.post('/instances/{instance_id}/optimise/scenario-a',response_model=SavedOptimiseResult)
def scenario_a(instance_id:UUID,payload:SavedOptimiseInput,request:Request,
               factory=Depends(optimisation_session_factory),
               x_demo_user_id:Annotated[UUID|None,Header()]=None):
    try:
        with factory() as db:
            with db.begin():
                actor=identity(request,db,x_demo_user_id)
                role(actor,'planner','administrator')
                instance=get_instance(db,actor,instance_id)
                options=store.resolve(db,actor,instance,payload)
                configuration=store.effective_configuration(instance,options,payload.baseline_run_id)
                digest=fingerprint(configuration)
                previous=store.existing_key(db,actor,instance_id,payload.idempotency_key,digest)
                reused=store.response(previous,False) if previous else None
        if reused is not None:return reused
        started=datetime.now(timezone.utc); clock=monotonic()
        computed=None
        try:
            computed=optimise(instance['dataset'],options)
            result=computed
            records=store.schedule_records(instance,options,result)
        except InputError:
            raise
        except Exception as exc:
            # Catch computation only, never reads, inserts or transaction commit errors.
            logger.exception('PS1 optimisation computation failed (%s)',request.state.correlation_id)
            result=OptimiseResult(solver_status='ERROR',solve_time_seconds=monotonic()-clock,
                failed_candidate={'diagnostic_only':True,'result_snapshot':computed.model_dump(mode='json')} if computed is not None else None,
                settings=configuration,diagnostics=[{'code':'handled_solver_error','error_type':type(exc).__name__,
                    'message':'Optimisation computation failed; use the correlation ID for server diagnostics.',
                    'correlation_id':request.state.correlation_id}])
            records={'accesses':[],'occupancies':[],'contract_results':[]}
        completed=datetime.now(timezone.utc)
        with factory() as db:
            with db.begin():
                # Recheck permissions and reset transaction-local actor/source/correlation.
                final_actor=identity(request,db,x_demo_user_id)
                role(final_actor,'planner','administrator')
                get_instance(db,final_actor,instance_id)
                if final_actor['operator_id']!=actor['operator_id']:
                    raise HTTPException(404,'PS1 instance not found')
                saved=store.persist(db,final_actor,instance,payload,configuration,digest,result,records,started,completed)
            # Deferred sealing and commit have succeeded before any success is returned.
        return saved
    except InputError as exc:raise HTTPException(422,str(exc)) from exc

@router.get('/instances/{instance_id}/optimisations',response_model=OptimisationPage)
def history(instance_id:UUID,db:DB,actor:Actor,limit:Limit=50,offset:Offset=0):
    get_instance(db,actor,instance_id)
    return repository.page(db,'''SELECT id,instance_id,baseline_run_id,scenario,solver_status,terminal_outcome,
        primary_optimal,lexicographic_complete,physical_validation_complete,publishable,
        objective_score::text AS objective_score,primary_objective_bound::text AS primary_objective_bound,
        primary_objective_gap::text AS primary_objective_gap,solve_duration_seconds,created_at
        FROM railplan.ps1_optimisation_runs WHERE instance_id=:instance AND operator_id=:op
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
