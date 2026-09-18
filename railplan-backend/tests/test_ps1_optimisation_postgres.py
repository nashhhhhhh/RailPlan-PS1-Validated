"""REAL committed PostgreSQL tests; never use SQLite or uncommitted-schema fakes.

TEST_COMMITTED_DATABASE_URL: empty disposable PostgreSQL16/PostGIS, railplan_test*.
The fixture commits and intentionally leaves its schema/data for inspection. Use a NEW
database next run. TEST_MIGRATION_DATABASE_URL is a separate empty disposable database.
Neither URL falls back to DATABASE_URL or TEST_DATABASE_URL. No destructive cleanup.
"""
import copy
import importlib
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from decimal import Decimal
from pathlib import Path
from threading import Barrier
from uuid import uuid4
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine,text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from alembic.migration import MigrationContext
from alembic.operations import Operations
from app.main import app
from app.database import session
from app.seed import seed,uid
from app.ps1 import parse_instance
from app.ps1_validation.persistence import get_instance
from app.ps1_validation.submission import fingerprint
from app.ps1_optimisation.contracts import OptimiseInput,OptimiseResult
from app.ps1_optimisation.saved_contracts import SavedOptimiseInput
from app.ps1_optimisation.service import optimise
from app.ps1_optimisation import persistence as store
from app.routers import ps1_optimisation as router
from scripts.create_ps1_smoke_fixture import files

ROOT=Path(__file__).resolve().parents[1]

def safe_url(key):
    url=os.environ.get(key)
    if not url:pytest.skip(f'{key} not configured: real committed PostgreSQL verification not executed')
    if not (make_url(url).database or '').startswith('railplan_test'):
        pytest.fail(f'{key} must name a disposable railplan_test* database')
    target=make_url(url)
    for other_key in ('TEST_DATABASE_URL','TEST_COMMITTED_DATABASE_URL','TEST_MIGRATION_DATABASE_URL'):
        if other_key!=key and os.environ.get(other_key):
            other=make_url(os.environ[other_key])
            if (target.host,target.port,target.database)==(other.host,other.port,other.database):
                pytest.fail('Rollback, committed and migration tests require three distinct disposable databases')
    return url

def require_empty(conn):
    if conn.execute(text("SELECT 1 FROM pg_namespace WHERE nspname='railplan'")).scalar():
        pytest.fail('Use a new empty database: railplan schema already exists; it will not be dropped')
    assert int(conn.execute(text('SHOW server_version_num')).scalar_one())>=160000

@pytest.fixture(scope='module')
def committed_engine():
    eng=create_engine(safe_url('TEST_COMMITTED_DATABASE_URL'),pool_pre_ping=True)
    with eng.begin() as conn:
        require_empty(conn)
        with Operations.context(MigrationContext.configure(conn)):
            for name in ('0001_initial','0002_api_support','0003_conflict_scoring','0004_analysis_history',
                         '0005_ps1_instances','0006_ps1_validations','0007_ps1_optimisation_runs','0008_ps1_scenario_b','0009_ps1_scenario_c'):
                importlib.import_module('migrations.versions.'+name).upgrade()
        seed(conn)
    yield eng
    eng.dispose()

@pytest.fixture(scope='module')
def fixture_instance(committed_engine):
    source=files();dataset=parse_instance(source)
    with committed_engine.begin() as conn:
        iid=conn.execute(text('''INSERT INTO railplan.ps1_instances(operator_id,imported_by,name,fingerprint,format_version,source_files,dataset)
            VALUES(:op,:actor,'Optimiser persistence smoke',:fp,:version,CAST(:source AS jsonb),CAST(:dataset AS jsonb)) RETURNING id'''),
            {'op':uid('operator'),'actor':uid('planner'),'fp':dataset['fingerprint'],'version':dataset['format_version'],
             'source':json.dumps(source),'dataset':json.dumps(dataset)}).scalar_one()
    return {'id':iid,'dataset':dataset}

@pytest.fixture(scope='module')
def good_result(fixture_instance):
    result=optimise(fixture_instance['dataset'],OptimiseInput(time_limit_seconds=5.0))
    assert result.publishable and result.physical_validation_complete
    return result

ACTOR={'id':uid('planner'),'operator_id':uid('operator'),'roles':{'planner'}}

def save(eng,instance,result,payload=None,records=None):
    payload=payload or SavedOptimiseInput()
    with Session(eng) as db,db.begin():options=store.resolve(db,ACTOR,instance,payload)
    config=store.effective_configuration(instance,options,payload.baseline_run_id)
    canonical=records if records is not None else store.schedule_records(instance,options,result)
    now=datetime.now(timezone.utc)
    with Session(eng) as db:
        with db.begin():
            db.execute(text("SELECT set_config('railplan.actor_id',:actor,true),set_config('railplan.source','ps1-test',true),set_config('railplan.correlation_id',:cid,true)"),{'actor':str(ACTOR['id']),'cid':str(uuid4())})
            saved=store.persist(db,ACTOR,instance,payload,config,fingerprint(config),result,canonical,now,now)
    return saved

@pytest.fixture
def api(committed_engine,monkeypatch):
    monkeypatch.setenv('RAILPLAN_DEMO_AUTH','1');monkeypatch.setenv('RAILPLAN_ENV','development')
    def db_session():
        with Session(committed_engine) as db,db.begin():yield db
    app.dependency_overrides[session]=db_session
    app.dependency_overrides[router.optimisation_session_factory]=lambda:lambda:Session(committed_engine)
    with TestClient(app,raise_server_exceptions=False) as client:
        client.headers['X-Demo-User-Id']=str(uid('planner'));yield client
    app.dependency_overrides.clear()

def test_fresh_connection_exact_snapshots_csvs_and_rows(committed_engine,fixture_instance,good_result):
    saved=save(committed_engine,fixture_instance,good_result)
    fresh_engine=create_engine(committed_engine.url)
    with Session(fresh_engine) as fresh:
        run=store.get_run(fresh,ACTOR,saved.run_id)
        assert run['result_snapshot']==good_result.model_dump(mode='json')
        assert run['validation_snapshot']==good_result.validation_report.model_dump(mode='json')
        assert run['accepted_csvs']==good_result.submission_files
        assert run['primary_optimal']==good_result.primary_optimal and run['lexicographic_complete']==good_result.lexicographic_complete
        for name in ('accesses','occupancies','contract_results'):
            actual=list(fresh.execute(text(f"SELECT to_jsonb(c)-'run_id'-'instance_id'-'operator_id' FROM railplan.ps1_optimisation_{name} c WHERE run_id=:id"),{'id':saved.run_id}).scalars())
            assert sorted(actual,key=str)==sorted(run['schedule_snapshot'][name],key=str)
    fresh_engine.dispose()

def test_scenario_b_api_persists_eclo_objective_physical_rows_and_exact_csvs(committed_engine,api):
    source=files()
    source['08_ACTIVITY_DETAILS.csv']=source['08_ACTIVITY_DETAILS.csv'].replace(',1,2027-01-04',',3,2027-01-04')
    source['07_PROJECT_DETAILS.csv']=source['07_PROJECT_DETAILS.csv'].replace('2027-01-10','2027-01-17')
    created=api.post('/api/ps1/instances',json={'files':source})
    assert created.status_code==201,created.text
    response=api.post(f"/api/ps1/instances/{created.json()['id']}/optimise/scenario-b",json={'time_limit_seconds':5,'random_seed':19})
    assert response.status_code==200,response.text
    body=response.json()
    assert body['scenario']=='B' and body['publishable']
    assert body['objective_components']['eclo_nights_total']==2
    assert body['validation_report']['objective_score']=='10.00'
    with Session(committed_engine) as db:
        run=store.get_run(db,ACTOR,body['run_id'])
        rows=list(db.execute(text('SELECT eclo,physical_night FROM railplan.ps1_optimisation_accesses WHERE run_id=:id ORDER BY access_seq'),{'id':body['run_id']}))
    assert run['scenario']=='B' and run['accepted_csvs']==body['submission_files']
    assert [row.eclo for row in rows]==[1,1]
    assert all(1<=row.physical_night<=7 for row in rows)

def test_scenario_c_api_persists_windows_weighted_objective_and_exact_csvs(committed_engine,api):
    source=files()
    source['08_ACTIVITY_DETAILS.csv']=source['08_ACTIVITY_DETAILS.csv'].replace(',1,2027-01-04',',3,2027-01-04')
    source['07_PROJECT_DETAILS.csv']=source['07_PROJECT_DETAILS.csv'].replace('Non-live (Others),3,2027','Non-live (Others),1,2027')
    created=api.post('/api/ps1/instances',json={'files':source})
    assert created.status_code==201,created.text
    response=api.post(f"/api/ps1/instances/{created.json()['id']}/optimise/scenario-c",json={'time_limit_seconds':5,'random_seed':23})
    assert response.status_code==200,response.text
    body=response.json()
    assert body['scenario']=='C' and body['publishable'] and body['eclo_windows']['ALP']['active']
    assert body['objective_components']['eclo_nights_total']==2
    with Session(committed_engine) as db:
        run=store.get_run(db,ACTOR,body['run_id'])
        rows=list(db.execute(text('SELECT eclo,physical_night FROM railplan.ps1_optimisation_accesses WHERE run_id=:id ORDER BY access_seq'),{'id':body['run_id']}))
    assert run['scenario']=='C' and run['accepted_csvs']==body['submission_files']
    assert run['result_snapshot']['eclo_windows']==body['eclo_windows']
    assert [row.eclo for row in rows]==[1,1] and all(1<=row.physical_night<=7 for row in rows)

def test_precision_and_primary_flags_roundtrip(committed_engine,fixture_instance):
    payload=SavedOptimiseInput(locked_placements=[{'activity_id':'SMOKE-A1','access_seq':1,'week':2,'physical_night':6,'access_night':1}])
    options=OptimiseInput.model_validate({k:getattr(payload,k) for k in OptimiseInput.model_fields})
    result=optimise(fixture_instance['dataset'],options)
    result.primary_optimal=True;result.lexicographic_complete=False;result.solver_status='FEASIBLE'
    saved=save(committed_engine,fixture_instance,result,payload)
    with Session(committed_engine) as db:
        run=store.get_run(db,ACTOR,saved.run_id)
        assert run['objective_score']==Decimal('9.10')
        assert run['primary_objective_bound']==Decimal('9.10')
        assert run['primary_objective_gap']==0 and run['primary_optimal'] and not run['lexicographic_complete']

@pytest.mark.parametrize('status',['FEASIBLE','UNKNOWN','INFEASIBLE','MODEL_LIMIT','VALIDATION_FAILED','ERROR','MODEL_INVALID'])
def test_terminal_outcomes_and_failed_downloads(committed_engine,fixture_instance,good_result,api,status):
    if status=='FEASIBLE':
        result=good_result.model_copy(deep=True);result.solver_status=status;result.primary_optimal=False;result.lexicographic_complete=False
    else:
        result=OptimiseResult(solver_status=status,solve_time_seconds=0,settings={},diagnostics=[{'code':'test_terminal'}])
        if status=='VALIDATION_FAILED':result.failed_candidate={'diagnostic_only':True,'submission_files':good_result.submission_files}
    payload=SavedOptimiseInput(idempotency_key=str(uuid4()))
    saved=save(committed_engine,fixture_instance,result,payload)
    assert save(committed_engine,fixture_instance,result,payload).run_id==saved.run_id
    detail=api.get(f'/api/ps1/optimisations/{saved.run_id}')
    assert detail.status_code==200 and detail.json()['result']==result.model_dump(mode='json')
    assert detail.json()['run']['terminal_outcome']==store.OUTCOMES[status]
    download=api.get(f'/api/ps1/optimisations/{saved.run_id}/artifacts')
    assert download.status_code==(200 if status=='FEASIBLE' else 409)
    if status!='FEASIBLE':
        assert api.get(f'/api/ps1/optimisations/{saved.run_id}/accesses').json()['total']==0
        assert api.get(f'/api/ps1/optimisations/{saved.run_id}/occupancies').json()['total']==0
        assert api.post(f'/api/ps1/instances/{fixture_instance["id"]}/optimise/scenario-a',json={'baseline_run_id':str(saved.run_id)}).status_code==422

def test_key_reuse_collision_and_new_attempt(committed_engine,fixture_instance,good_result):
    key=str(uuid4());payload=SavedOptimiseInput(idempotency_key=key)
    first=save(committed_engine,fixture_instance,good_result,payload)
    again=save(committed_engine,fixture_instance,good_result,payload)
    assert first.created and again.reused and first.run_id==again.run_id
    with pytest.raises(HTTPException) as exc:save(committed_engine,fixture_instance,good_result,SavedOptimiseInput(idempotency_key=key,random_seed=1))
    assert exc.value.status_code==409
    different=save(committed_engine,fixture_instance,good_result,SavedOptimiseInput(idempotency_key=str(uuid4())))
    assert different.created and different.run_id!=first.run_id and different.input_fingerprint==first.input_fingerprint

def test_concurrent_connections_one_result_per_key(committed_engine,fixture_instance,good_result):
    payload=SavedOptimiseInput(idempotency_key=str(uuid4()));barrier=Barrier(2)
    def submit():
        barrier.wait(timeout=10)
        return save(committed_engine,fixture_instance,good_result,payload)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(submit) for _ in range(2)]
        results=[f.result(timeout=30) for f in futures]
    assert results[0].run_id==results[1].run_id and sum(r.created for r in results)==1
    with Session(committed_engine) as db:
        assert db.execute(text('SELECT count(*) FROM railplan.ps1_optimisation_keys WHERE idempotency_key=:key'),{'key':payload.idempotency_key}).scalar_one()==1
        assert db.execute(text("SELECT count(*) FROM railplan.ps1_optimisation_runs WHERE request_snapshot->>'idempotency_key'=:key"),{'key':payload.idempotency_key}).scalar_one()==1

def test_child_failure_rolls_back_run_key_audit_and_event(committed_engine,fixture_instance,good_result):
    tables=['ps1_optimisation_runs','ps1_optimisation_accesses','ps1_optimisation_occupancies','ps1_optimisation_contract_results','ps1_optimisation_keys','audit_logs','activity_events']
    def counts():
        with Session(committed_engine) as db:return [db.execute(text(f'SELECT count(*) FROM railplan.{t}')).scalar_one() for t in tables]
    before=counts()
    records=store.schedule_records(fixture_instance,OptimiseInput(),good_result)
    records['occupancies'].append(dict(records['occupancies'][0]))
    with pytest.raises(DBAPIError):save(committed_engine,fixture_instance,good_result,SavedOptimiseInput(idempotency_key=str(uuid4())),records)
    assert counts()==before

def test_deferred_seal_failure_rolls_back_even_key_and_event(committed_engine,fixture_instance,good_result,monkeypatch):
    tables=['ps1_optimisation_runs','ps1_optimisation_accesses','ps1_optimisation_occupancies','ps1_optimisation_contract_results','ps1_optimisation_keys','audit_logs','activity_events']
    def counts():
        with committed_engine.connect() as db:return [db.execute(text(f'SELECT count(*) FROM railplan.{t}')).scalar_one() for t in tables]
    before=counts();real=Session.execute;seen=[]
    def skip_child(self,statement,*args,**kwargs):
        query=str(statement)
        if 'INSERT INTO railplan.ps1_optimisation_occupancies' in query:
            return real(self,text('SELECT 1'))
        if 'INSERT INTO railplan.ps1_optimisation_keys' in query or 'INSERT INTO railplan.activity_events' in query:seen.append(query)
        return real(self,statement,*args,**kwargs)
    monkeypatch.setattr(Session,'execute',skip_child)
    with pytest.raises(DBAPIError,match='Incomplete or inconsistent sealed'):
        save(committed_engine,fixture_instance,good_result,SavedOptimiseInput(idempotency_key=str(uuid4())))
    assert len(seen)==2 and counts()==before

@pytest.mark.parametrize('table',['runs','accesses','occupancies','contract_results','keys'])
@pytest.mark.parametrize('operation',['UPDATE','DELETE','TRUNCATE'])
def test_terminal_tables_are_immutable(committed_engine,fixture_instance,good_result,table,operation):
    saved=save(committed_engine,fixture_instance,good_result,SavedOptimiseInput(idempotency_key=str(uuid4())))
    column='id' if table=='runs' else 'run_id'
    query=f'UPDATE railplan.ps1_optimisation_{table} SET {column}={column} WHERE {column}=:id' if operation=='UPDATE' else (
        f'DELETE FROM railplan.ps1_optimisation_{table} WHERE {column}=:id' if operation=='DELETE' else f'TRUNCATE railplan.ps1_optimisation_{table} CASCADE')
    with pytest.raises(DBAPIError):
        with committed_engine.begin() as conn:conn.execute(text(query),{'id':saved.run_id})

@pytest.mark.parametrize('table',['accesses','occupancies','contract_results','keys'])
def test_later_child_insert_blocked(committed_engine,fixture_instance,good_result,table):
    saved=save(committed_engine,fixture_instance,good_result,SavedOptimiseInput(idempotency_key=str(uuid4())))
    # Same rows deliberately copied: BEFORE INSERT sealing must reject before uniqueness.
    with pytest.raises(DBAPIError,match='sealed'):
        with committed_engine.begin() as conn:
            conn.execute(text(f'INSERT INTO railplan.ps1_optimisation_{table} SELECT * FROM railplan.ps1_optimisation_{table} WHERE run_id=:id'),{'id':saved.run_id})

def test_api_baseline_pagination_download_and_no_reexecution(api,fixture_instance,monkeypatch):
    path=f'/api/ps1/instances/{fixture_instance["id"]}/optimise/scenario-a';key=str(uuid4())
    first=api.post(path,json={'idempotency_key':key,'time_limit_seconds':5})
    assert first.status_code==200,first.text
    body=first.json();assert body['publishable']
    original=router.optimise
    def forbid(*args):raise AssertionError('Solver must not execute on idempotent retry')
    monkeypatch.setattr(router,'optimise',forbid)
    again=api.post(path,json={'idempotency_key':key,'time_limit_seconds':5})
    assert again.status_code==200 and again.json()['run_id']==body['run_id'] and again.json()['reused']
    assert api.post(path,json={'idempotency_key':key,'random_seed':1}).status_code==409
    monkeypatch.setattr(router,'optimise',original)
    baseline=api.post(path,json={'baseline_run_id':body['run_id'],'time_limit_seconds':5})
    assert baseline.status_code==200,baseline.text
    assert baseline.json()['publishable']
    records=api.get(f'/api/ps1/optimisations/{baseline.json()["run_id"]}/accesses?week=1&limit=1').json()
    assert records['total']==1 and records['items'][0]['baseline_week']==1
    assert api.get(f'/api/ps1/optimisations/{body["run_id"]}/artifacts').json()['files']==body['submission_files']
    history=f'/api/ps1/instances/{fixture_instance["id"]}/optimisations'
    page=api.get(history+'?limit=1').json();next_page=api.get(history+'?limit=1&offset=1').json()
    assert page['items'][0]['id']!=next_page['items'][0]['id']
    assert api.get(history+'?limit=1').json()==page

def test_operator_and_instance_scope_all_routes(api,committed_engine,fixture_instance,good_result):
    saved=save(committed_engine,fixture_instance,good_result)
    otherop,department,user=uuid4(),uuid4(),uuid4()
    source=files();dataset=parse_instance(source)
    with committed_engine.begin() as conn:
        conn.execute(text("INSERT INTO railplan.operators(id,code,name) VALUES(:id,:code,'Other')"),{'id':otherop,'code':str(otherop)})
        conn.execute(text("INSERT INTO railplan.departments(id,operator_id,name) VALUES(:id,:op,'Other')"),{'id':department,'op':otherop})
        conn.execute(text("INSERT INTO railplan.users(id,department_id,auth_subject,display_name) VALUES(:id,:d,:subject,'Other')"),{'id':user,'d':department,'subject':str(user)})
        conn.execute(text('INSERT INTO railplan.user_roles(user_id,role_id) VALUES(:u,:r)'),{'u':user,'r':uid('role/planner')})
    api.headers['X-Demo-User-Id']=str(user)
    for suffix in ('','/accesses','/occupancies','/artifacts'):
        assert api.get(f'/api/ps1/optimisations/{saved.run_id}{suffix}').status_code==404
    assert api.get(f'/api/ps1/instances/{fixture_instance["id"]}/optimisations').status_code==404
    assert api.post(f'/api/ps1/instances/{fixture_instance["id"]}/optimise/scenario-a',json={}).status_code==404
    other_instance=api.post('/api/ps1/instances',json={'files':source}).json()['id']
    assert api.post(f'/api/ps1/instances/{other_instance}/optimise/scenario-a',json={'baseline_run_id':str(saved.run_id)}).status_code==404
    # Same key text has a separate operator/instance scope.
    key=str(uuid4())
    first=api.post(f'/api/ps1/instances/{other_instance}/optimise/scenario-a',json={'idempotency_key':key,'time_limit_seconds':5})
    api.headers['X-Demo-User-Id']=str(uid('planner'))
    second=api.post(f'/api/ps1/instances/{fixture_instance["id"]}/optimise/scenario-a',json={'idempotency_key':key,'time_limit_seconds':5})
    assert first.status_code==second.status_code==200
    assert first.json()['run_id']!=second.json()['run_id']
    source['08_ACTIVITY_DETAILS.csv']=source['08_ACTIVITY_DETAILS.csv'].replace('SMOKE-A1','SMOKE-A2')
    new_instance=api.post('/api/ps1/instances',json={'files':source}).json()['id']
    assert api.post(f'/api/ps1/instances/{new_instance}/optimise/scenario-a',json={'baseline_run_id':str(saved.run_id)}).status_code==404

def test_migration_upgrade_and_deliberate_downgrade_refusal():
    url=safe_url('TEST_MIGRATION_DATABASE_URL')
    other=os.environ.get('TEST_COMMITTED_DATABASE_URL')
    if other and (make_url(other).host,make_url(other).port,make_url(other).database)==(make_url(url).host,make_url(url).port,make_url(url).database):
        pytest.fail('Migration database must be separate from committed-test database')
    eng=create_engine(url)
    with eng.begin() as conn:require_empty(conn)
    env={**os.environ,'DATABASE_URL':url}
    upgraded=subprocess.run([sys.executable,'-m','alembic','upgrade','head'],cwd=ROOT,env=env,capture_output=True,text=True)
    assert upgraded.returncode==0,upgraded.stderr
    repeated=subprocess.run([sys.executable,'-m','alembic','upgrade','head'],cwd=ROOT,env=env,capture_output=True,text=True)
    assert repeated.returncode==0,repeated.stderr
    for module in ('app.seed','app.seed_scoring'):
        seeded=subprocess.run([sys.executable,'-m',module],cwd=ROOT,env=env,capture_output=True,text=True)
        assert seeded.returncode==0,seeded.stderr
    with eng.connect() as conn:
        assert conn.execute(text('SELECT version_num FROM alembic_version')).scalar_one()=='0009'
        assert conn.execute(text("SELECT count(*) FROM pg_tables WHERE schemaname='railplan' AND tablename LIKE 'ps1_optimisation_%'")).scalar_one()==5
    refused=subprocess.run([sys.executable,'-m','alembic','downgrade','0008'],cwd=ROOT,env=env,capture_output=True,text=True)
    assert refused.returncode!=0 and 'Archive sealed Scenario C optimisation evidence' in refused.stderr
    with eng.connect() as conn:assert conn.execute(text('SELECT version_num FROM alembic_version')).scalar_one()=='0009'
    eng.dispose()
