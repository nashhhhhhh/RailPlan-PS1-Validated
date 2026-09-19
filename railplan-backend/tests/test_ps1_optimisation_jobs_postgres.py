"""Committed B/C job verification on an explicitly disposable PostgreSQL database."""
import importlib
import json
import os
import time
from pathlib import Path
from threading import Event
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine,text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.database import session
from app.main import app
from app.ps1 import parse_instance
from app.ps1_optimisation.contracts import OptimiseResult
from app.ps1_optimisation import jobs as job_runner
from app.routers import ps1_optimisation as router
from app.seed import seed,uid
from scripts.create_ps1_smoke_fixture import files


def wait_job(client,job_id,seconds=20):
    seen=[];deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        response=client.get(f'/api/ps1/optimisation-jobs/{job_id}')
        assert response.status_code==200,response.text
        job=response.json();seen.append(job['progress'])
        if job['status'] in ('SUCCEEDED','FAILED','CANCELLED'):
            assert seen==sorted(seen)
            return job
        time.sleep(.03)
    pytest.fail('Optimisation job did not become terminal')


@pytest.fixture(scope='module')
def async_job_database():
    url=os.environ.get('TEST_ASYNC_JOBS_DATABASE_URL')
    if not url:pytest.skip('TEST_ASYNC_JOBS_DATABASE_URL not configured: committed B/C job tests not executed')
    if not (make_url(url).database or '').startswith('railplan_test'):
        pytest.fail('TEST_ASYNC_JOBS_DATABASE_URL must name a disposable railplan_test* database')
    eng=create_engine(url,pool_pre_ping=True)
    with eng.begin() as conn:
        if conn.execute(text("SELECT 1 FROM pg_namespace WHERE nspname='railplan'")).scalar():
            pytest.fail('Use a new empty database; the async-job tests never drop existing data')
        with Operations.context(MigrationContext.configure(conn)):
            for name in ('0001_initial','0002_api_support','0003_conflict_scoring','0004_analysis_history',
                         '0005_ps1_instances','0006_ps1_validations','0007_ps1_optimisation_runs',
                         '0008_ps1_scenario_b','0009_ps1_scenario_c','0010_ps1_optimisation_jobs',
                         '0011_ps1_optimisation_job_guards'):
                importlib.import_module('migrations.versions.'+name).upgrade()
        seed(conn)
        source=files();dataset=parse_instance(source)
        instance_id=conn.execute(text('''INSERT INTO railplan.ps1_instances
          (operator_id,imported_by,name,fingerprint,format_version,source_files,dataset)
          VALUES(:op,:actor,'Async B/C smoke',:fingerprint,:version,CAST(:source AS jsonb),CAST(:dataset AS jsonb)) RETURNING id'''),
          {'op':uid('operator'),'actor':uid('planner'),'fingerprint':dataset['fingerprint'],
           'version':dataset['format_version'],'source':json.dumps(source),'dataset':json.dumps(dataset)}).scalar_one()
    yield eng,instance_id,source
    eng.dispose()


@pytest.fixture
def async_api(async_job_database,monkeypatch):
    eng,instance_id,source=async_job_database
    monkeypatch.setenv('RAILPLAN_DEMO_AUTH','1');monkeypatch.setenv('RAILPLAN_ENV','development')
    def db_session():
        with Session(eng) as db,db.begin():yield db
    app.dependency_overrides[session]=db_session
    app.dependency_overrides[router.optimisation_session_factory]=lambda:lambda:Session(eng)
    with TestClient(app,raise_server_exceptions=False) as client:
        client.headers['X-Demo-User-Id']=str(uid('planner'))
        yield client,eng,instance_id,source
    app.dependency_overrides.clear()


def test_scenario_b_c_start_poll_idempotency_artifacts_and_order(async_api):
    client,_,instance_id,source=async_api;key='shared-'+str(uuid4())
    jobs_by_scenario={}
    for scenario in ('a','b','c'):
        path=f'/api/ps1/instances/{instance_id}/optimise/scenario-{scenario}/jobs'
        response=client.post(path,json={'idempotency_key':key,'time_limit_seconds':5,'random_seed':31})
        assert response.status_code==202,response.text
        jobs_by_scenario[scenario]=wait_job(client,response.json()['job']['id'])
        assert jobs_by_scenario[scenario]['status']=='SUCCEEDED'
        replay=client.post(path,json={'idempotency_key':key,'time_limit_seconds':5,'random_seed':31})
        assert replay.status_code==202 and replay.json()['reused']
    assert len({job['id'] for job in jobs_by_scenario.values()})==3
    collision=client.post(f'/api/ps1/instances/{instance_id}/optimise/scenario-b/jobs',
        json={'idempotency_key':key,'time_limit_seconds':6,'random_seed':31})
    assert collision.status_code==409
    for job in jobs_by_scenario.values():
        artifacts=client.get(f'/api/ps1/optimisations/{job["run_id"]}/artifacts')
        assert artifacts.status_code==(200 if job['artifact_eligible'] else 409)
    listing=client.get(f'/api/ps1/instances/{instance_id}/optimisation-jobs').json()['items']
    assert [item['created_at'] for item in listing]==sorted((item['created_at'] for item in listing),reverse=True)
    assert client.post(f'/api/ps1/optimise/scenario-c/preview',json={'instance_files':source,'time_limit_seconds':2}).status_code==200
    assert client.post(f'/api/ps1/instances/{instance_id}/optimise/scenario-b',json={'time_limit_seconds':2}).status_code==200


def test_queued_running_and_terminal_cancellation(async_api,monkeypatch):
    client,_,instance_id,_=async_api;gate=Event()
    def slow(*_args,**_kwargs):
        gate.wait(10)
        return OptimiseResult(solver_status='UNKNOWN',solve_time_seconds=0,settings={})
    monkeypatch.setattr(router,'optimise',slow)
    path=f'/api/ps1/instances/{instance_id}/optimise/scenario-a/jobs'
    blockers=[client.post(path,json={'idempotency_key':str(uuid4())}).json()['job']['id']
              for _ in range(job_runner._workers)]
    for running in blockers:
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            if client.get(f'/api/ps1/optimisation-jobs/{running}').json()['status']=='RUNNING':break
            time.sleep(.03)
    queued=client.post(path,json={'idempotency_key':str(uuid4())}).json()['job']['id']
    assert client.post(f'/api/ps1/optimisation-jobs/{queued}/cancel').json()['status']=='CANCELLED'
    for running in blockers:
        assert client.post(f'/api/ps1/optimisation-jobs/{running}/cancel').json()['cancel_requested']
    gate.set()
    for running in blockers:
        assert wait_job(client,running)['status']=='CANCELLED'
        assert client.post(f'/api/ps1/optimisation-jobs/{running}/cancel').status_code==409


def test_failure_unknown_and_validator_rejection_persist_without_artifacts(async_api,monkeypatch):
    client,_,instance_id,_=async_api
    path=f'/api/ps1/instances/{instance_id}/optimise/scenario-b/jobs'
    monkeypatch.setattr(router,'optimise_scenario_b',lambda *_args,**_kwargs:(_ for _ in ()).throw(RuntimeError('test failure')))
    failed=client.post(path,json={'idempotency_key':str(uuid4())}).json()['job']['id']
    assert wait_job(client,failed)['status']=='FAILED'
    for status in ('UNKNOWN','VALIDATION_FAILED'):
        monkeypatch.setattr(router,'optimise_scenario_b',lambda *_args,_status=status,**_kwargs:
            OptimiseResult(scenario='B',solver_status=_status,solve_time_seconds=0,settings={},
                failed_candidate={'diagnostic_only':True} if _status=='VALIDATION_FAILED' else None))
        job=wait_job(client,client.post(path,json={'idempotency_key':str(uuid4())}).json()['job']['id'])
        assert job['status']=='SUCCEEDED' and job['solver_status']==status and not job['artifact_eligible']
        assert client.get(f'/api/ps1/optimisations/{job["run_id"]}/artifacts').status_code==409


def test_job_operator_isolation(async_api):
    client,eng,instance_id,_=async_api
    job=client.post(f'/api/ps1/instances/{instance_id}/optimise/scenario-c/jobs',json={'idempotency_key':str(uuid4())}).json()['job']
    wait_job(client,job['id'])
    otherop,department,user=uuid4(),uuid4(),uuid4()
    with eng.begin() as conn:
        conn.execute(text("INSERT INTO railplan.operators(id,code,name) VALUES(:id,:code,'Other')"),{'id':otherop,'code':str(otherop)})
        conn.execute(text("INSERT INTO railplan.departments(id,operator_id,name) VALUES(:id,:op,'Other')"),{'id':department,'op':otherop})
        conn.execute(text("INSERT INTO railplan.users(id,department_id,auth_subject,display_name) VALUES(:id,:d,:subject,'Other')"),{'id':user,'d':department,'subject':str(user)})
        conn.execute(text('INSERT INTO railplan.user_roles(user_id,role_id) VALUES(:u,:r)'),{'u':user,'r':uid('role/planner')})
    client.headers['X-Demo-User-Id']=str(user)
    assert client.get(f'/api/ps1/optimisation-jobs/{job["id"]}').status_code==404
    assert client.post(f'/api/ps1/optimisation-jobs/{job["id"]}/cancel').status_code==404
