"""Database-free contract checks for the shared A/B/C job layer.

Committed lifecycle behaviour remains covered by the PostgreSQL suite and is skipped
when its explicitly disposable URLs are absent.
"""
import inspect
from datetime import datetime,timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.main import app
from app.ps1_optimisation import jobs
from app.ps1_optimisation.saved_contracts import OptimisationJob
from app.routers import ps1_optimisation as router


def base_row(**changes):
    now=datetime.now(timezone.utc)
    row={'id':uuid4(),'instance_id':uuid4(),'operator_id':uuid4(),'created_by':uuid4(),
        'scenario':'B','status':'QUEUED','progress':0,'stage':'queued','cancel_requested':False,
        'run_id':None,'input_fingerprint':'a'*64,'diagnostic':None,
        'request_snapshot':{'schema_version':2,'capture':{'solver_seed':17,'time_limit_seconds':4.5,
            'deterministic_time_limit':2.5,'option_snapshot':{'random_seed':17},
            'validator_version':'validator/1','policy_version':'policy/1'}},
        'created_at':now,'started_at':None,'completed_at':None,'updated_at':now}
    row.update(changes)
    return row


def test_start_scenario_b_and_c_jobs_share_dispatch(monkeypatch):
    seen=[]
    monkeypatch.setattr(router,'_start_job',lambda *args:seen.append(args[-1]) or args[-1])
    assert router.scenario_b_job('i','p','r','f','u')=='B'
    assert router.scenario_c_job('i','p','r','f','u')=='C'
    assert seen==['B','C']


def test_all_job_and_existing_endpoint_paths_remain_available():
    paths=app.openapi()['paths']
    for scenario in 'abc':
        assert f'/api/ps1/instances/{{instance_id}}/optimise/scenario-{scenario}/jobs' in paths
        assert f'/api/ps1/instances/{{instance_id}}/optimise/scenario-{scenario}' in paths
        assert f'/api/ps1/optimise/scenario-{scenario}/preview' in paths
    assert '/api/ps1/optimisation-jobs/{job_id}' in paths
    assert '/api/ps1/optimisation-jobs/{job_id}/cancel' in paths


def test_scenario_specific_idempotency_is_explicit_in_start_query():
    key='client-retry-key'
    assert len({router._idempotency_token(s,key) for s in 'ABC'})==3
    source=inspect.getsource(router._start_job)
    assert 'instance_id=:instance AND scenario=:scenario' in source
    assert '/{scenario}/' in source


def test_job_snapshot_captures_bounded_reproducible_inputs():
    class Payload:
        def model_dump(self,**_):return {'idempotency_key':'retry'}
    configuration={'solver_options':{'random_seed':9,'time_limit_seconds':12.0,'deterministic_time_limit':3.0},
        'validator_version':'v','policy_version':'p','optimiser_version':'o','objective_policy':'objective',
        'dataset_fingerprint':'d'}
    capture=router._job_capture(Payload(),configuration)
    assert capture['capture']['option_snapshot']==configuration['solver_options']
    assert capture['capture']['solver_seed']==9
    assert capture['capture']['validator_version']=='v'


@pytest.mark.parametrize('scenario',['A','B','C'])
def test_poll_view_preserves_scenario_and_progress(scenario):
    job=OptimisationJob.model_validate(router._job_view(base_row(scenario=scenario,progress=85,status='RUNNING')))
    assert job.scenario==scenario and job.progress==85 and job.solver_seed==17


def test_unknown_without_incumbent_has_no_artifact_eligibility():
    job=OptimisationJob.model_validate(router._job_view(base_row(status='SUCCEEDED',progress=100,
        solver_status='UNKNOWN',artifact_eligible=False,objective_components=None)))
    assert job.solver_status=='UNKNOWN' and not job.artifact_eligible


def test_validator_rejection_has_no_artifact_eligibility():
    job=OptimisationJob.model_validate(router._job_view(base_row(status='SUCCEEDED',progress=100,
        solver_status='VALIDATION_FAILED',artifact_eligible=False,
        validation_result={'feasible':False,'hard_violations':[{'code':'test'}]})))
    assert not job.artifact_eligible and job.validation_result['hard_violations']


def test_validated_feasible_terminal_evidence_is_artifact_eligible():
    job=OptimisationJob.model_validate(router._job_view(base_row(status='SUCCEEDED',progress=100,
        solver_status='FEASIBLE',artifact_eligible=True,best_objective='10.00',best_bound='9.00',
        validation_result={'feasible':True,'physical_validation_complete':True,'hard_violations':[]})))
    assert job.artifact_eligible and job.best_objective=='10.00'


def test_failure_diagnostics_survive_poll_view():
    diagnostic={'code':'job_execution_failed','correlation_id':str(uuid4())}
    job=OptimisationJob.model_validate(router._job_view(base_row(status='FAILED',diagnostic=diagnostic)))
    assert job.diagnostic==diagnostic and job.run_id is None


def test_cancel_terminal_job_is_rejected(monkeypatch):
    monkeypatch.setattr(router,'role',lambda *_:None)
    monkeypatch.setattr(router,'_recover_abandoned',lambda *_:None)
    monkeypatch.setattr(router,'_job_record',lambda *_args,**_kwargs:base_row(status='SUCCEEDED'))
    with pytest.raises(HTTPException) as caught:
        router.cancel_optimisation_job(uuid4(),object(),{'roles':{'planner'}})
    assert caught.value.status_code==409


def test_queued_registry_supports_cooperative_cancel_and_restart_detection():
    job_id=uuid4();jobs.reserve(job_id)
    try:
        assert jobs.active(job_id)
        jobs.request_cancel(job_id)
        # A reservation remains known until the transaction owner releases it.
        assert jobs.active(job_id)
    finally:jobs.release(job_id)
    assert not jobs.active(job_id)


def test_progress_guard_and_stable_ordering_are_explicit():
    source=inspect.getsource(router.optimisation_jobs)
    assert 'ORDER BY j.created_at DESC,j.id DESC' in source
    guard=(router.__file__.replace('app\\routers\\ps1_optimisation.py','sql\\014_ps1_optimisation_job_guards.sql'))
    # Avoid depending on platform separators when this suite runs on Linux.
    if guard==router.__file__:guard=router.__file__.replace('app/routers/ps1_optimisation.py','sql/014_ps1_optimisation_job_guards.sql')
    assert 'progress cannot decrease' in open(guard,encoding='utf-8').read()
