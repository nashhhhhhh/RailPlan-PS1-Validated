"""Run ONLY with an empty disposable PostgreSQL 16+PostGIS database.
TEST_DATABASE_URL must name a database starting with railplan_test.
All DDL and test data roll back at the end. No existing schema is dropped.
"""
import os
from pathlib import Path
from datetime import timedelta
import pytest
from sqlalchemy import create_engine,text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from app.seed import seed,uid
from app.queries import QUERIES
from app.models import Base

@pytest.fixture(scope="module")
def connection():
    url=os.environ.get("TEST_DATABASE_URL")
    if not url: pytest.skip("TEST_DATABASE_URL not set: PostgreSQL/PostGIS integration not executed")
    if not (make_url(url).database or "").startswith("railplan_test"):
        pytest.fail("Use a disposable database whose name starts with railplan_test")
    engine=create_engine(url)
    with engine.connect() as conn:
        transaction=conn.begin()
        exists=conn.execute(text("SELECT 1 FROM pg_namespace WHERE nspname='railplan'")).scalar()
        if exists: pytest.fail("Test database must not already contain the railplan schema")
        root=Path(__file__).resolve().parents[1]
        for f in ("001_schema.sql","002_guards.sql","003_views.sql"):
            conn.exec_driver_sql((root/"sql"/f).read_text(), execution_options={"no_parameters": True})
        from alembic.migration import MigrationContext
        from alembic.operations import Operations
        import importlib
        with Operations.context(MigrationContext.configure(conn)):
            importlib.import_module("migrations.versions.0002_api_support").upgrade()
            importlib.import_module("migrations.versions.0003_conflict_scoring").upgrade()
            importlib.import_module("migrations.versions.0004_analysis_history").upgrade()
            importlib.import_module("migrations.versions.0005_ps1_instances").upgrade()
            importlib.import_module("migrations.versions.0006_ps1_validations").upgrade()
            importlib.import_module("migrations.versions.0007_ps1_optimisation_runs").upgrade()
        seed(conn)
        from app.demo_rules import configure_demo_rules
        configure_demo_rules(conn)
        yield conn
        transaction.rollback()
    engine.dispose()

@pytest.fixture
def db(connection):
    txn=connection.begin_nested()
    yield connection
    txn.rollback()

def run(db,key,**params):
    return db.execute(text(QUERIES[key]),params).mappings().all()

def test_postgres_version(db):
    assert int(db.execute(text("SHOW server_version_num")).scalar())>=160000
    assert db.execute(text("SELECT postgis_version()")).scalar()

def test_ps1_persistence_dedup_and_exact_csv_retention(api,db):
    from app.ps1 import load_files
    payload={'name':'PS1 test','files':load_files()}
    first=api.post('/api/ps1/instances',json=payload)
    assert first.status_code==200,first.text
    assert first.json()['created']
    second=api.post('/api/ps1/instances',json=payload)
    assert second.json()['id']==first.json()['id'] and not second.json()['created']
    result=api.get('/api/ps1/instances/'+first.json()['id'])
    assert result.status_code==200 and result.json()['dataset']['summary']['activities']==54
    stored=db.execute(text('SELECT source_files FROM railplan.ps1_instances WHERE id=:id'),{'id':first.json()['id']}).scalar_one()
    assert stored==payload['files']
    with pytest.raises(DBAPIError):
        with db.begin_nested():db.execute(text('DELETE FROM railplan.ps1_instances'))

def test_ps1_operator_scope_and_viewer_cannot_import(api,db):
    from app.ps1 import load_files
    from uuid import uuid4
    payload={'files':load_files()}
    result=api.post('/api/ps1/instances',json=payload)
    assert result.status_code==200,result.text
    operator,department,user=uuid4(),uuid4(),uuid4()
    db.execute(text("INSERT INTO railplan.operators(id,code,name) VALUES(:id,'PS1-OTHER','Other')"),{'id':operator})
    db.execute(text("INSERT INTO railplan.departments(id,operator_id,name) VALUES(:id,:op,'Other')"),{'id':department,'op':operator})
    db.execute(text("INSERT INTO railplan.users(id,department_id,auth_subject,display_name) VALUES(:id,:d,'ps1-test-viewer','Viewer')"),{'id':user,'d':department})
    db.execute(text("INSERT INTO railplan.user_roles(user_id,role_id) VALUES(:u,:r)"),{'u':user,'r':uid('role/viewer')})
    api.headers['X-Demo-User-Id']=str(user)
    assert api.get('/api/ps1/instances').json()['total']==0
    assert api.get('/api/ps1/instances/'+result.json()['id']).status_code==404
    assert api.post('/api/ps1/instances',json=payload).status_code==403

@pytest.fixture
def validation_run(api,db):
    from app.ps1 import load_files
    from test_ps1_validation import sample_files
    instance=api.post('/api/ps1/instances',json={'files':load_files()}).json()['id']
    payload={'scenario':'A','files':sample_files(),'idempotency_key':'ps1-first-key'}
    path=f'/api/ps1/instances/{instance}/validations'
    response=api.post(path,json=payload)
    assert response.status_code==200,response.text
    return path,payload,response.json()

def test_ps1_optimiser_saved_without_mutating_dataset_or_validation_history(api,db):
    from app.ps1 import load_files
    imported=api.post('/api/ps1/instances',json={'files':load_files()})
    assert imported.status_code==200,imported.text
    instance=imported.json()['id']
    before=db.execute(text('SELECT dataset,source_files FROM railplan.ps1_instances WHERE id=:id'),{'id':instance}).one()
    count=db.execute(text('SELECT count(*) FROM railplan.ps1_validation_runs')).scalar_one()
    result=api.post(f'/api/ps1/instances/{instance}/optimise/scenario-a',json={'time_limit_seconds':0.1,'deterministic_time_limit':0.001})
    assert result.status_code==200,result.text
    assert result.json()['judge_validation']=='not_run'
    assert result.json()['solver_status']=='UNKNOWN' and result.json()['submission_files'] is None
    assert result.json()['created'] and result.json()['run_id']
    saved=api.get('/api/ps1/optimisations/'+result.json()['run_id'])
    assert saved.status_code==200 and saved.json()['result']['solver_status']=='UNKNOWN'
    assert db.execute(text('SELECT dataset,source_files FROM railplan.ps1_instances WHERE id=:id'),{'id':instance}).one()==before
    assert db.execute(text('SELECT count(*) FROM railplan.ps1_validation_runs')).scalar_one()==count

def test_ps1_optimiser_cross_operator_and_viewer_denied(api,db):
    from app.ps1 import load_files
    from uuid import uuid4
    instance=api.post('/api/ps1/instances',json={'files':load_files()}).json()['id']
    operator,department,user=uuid4(),uuid4(),uuid4()
    db.execute(text("INSERT INTO railplan.operators(id,code,name) VALUES(:id,'OPT-OTHER','Other')"),{'id':operator})
    db.execute(text("INSERT INTO railplan.departments(id,operator_id,name) VALUES(:id,:op,'Other')"),{'id':department,'op':operator})
    db.execute(text("INSERT INTO railplan.users(id,department_id,auth_subject,display_name) VALUES(:id,:d,'opt-other','Other')"),{'id':user,'d':department})
    db.execute(text('INSERT INTO railplan.user_roles(user_id,role_id) VALUES(:u,:r)'),{'u':user,'r':uid('role/planner')})
    api.headers['X-Demo-User-Id']=str(user)
    path=f'/api/ps1/instances/{instance}/optimise/scenario-a'
    assert api.post(path,json={}).status_code==404
    db.execute(text('DELETE FROM railplan.user_roles WHERE user_id=:u'),{'u':user})
    db.execute(text('INSERT INTO railplan.user_roles(user_id,role_id) VALUES(:u,:r)'),{'u':user,'r':uid('role/viewer')})
    assert api.post(path,json={}).status_code==403

def test_ps1_validation_exact_sources_dedup_and_audit(api,db,validation_run):
    path,payload,result=validation_run
    again=api.post(path,json=payload).json()
    assert again['id']==result['id'] and not again['created']
    payload['idempotency_key']='alias-key'
    assert api.post(path,json=payload).json()['id']==result['id']
    payload['scenario']='B'
    assert api.post(path,json=payload).status_code==409
    stored=api.get('/api/ps1/validations/'+result['id']).json()
    assert stored['source_files']==payload['files']
    assert stored['result_snapshot']==result['report']
    assert stored['policy_snapshot']==result['report']['rule_policy']
    assert api.get(path).json()['total']==1
    violations=api.get('/api/ps1/validations/'+result['id']+'/violations').json()
    assert violations['total']==0
    assert len(result['report']['warnings'])==70
    assert [r['evidence_snapshot'] for r in violations['items']]==result['report']['hard_violations'][:50]
    assert api.get('/api/ps1/validations/'+result['id']+'/violations?rule_code=workload').json()['total']==0
    assert db.execute(text("SELECT count(*) FROM railplan.audit_logs WHERE entity_type='ps1_validation_runs'")).scalar()>=1

def test_ps1_validation_key_content_collision(api,validation_run):
    path,payload,result=validation_run
    payload['files']['RESULTS.csv']+='\n'
    response=api.post(path,json=payload)
    assert response.status_code==409
    assert response.json()['error']['code']=='STATE_CONFLICT'

@pytest.mark.parametrize('table',['ps1_validation_runs','ps1_validation_violations','ps1_validation_keys'])
@pytest.mark.parametrize('operation',['UPDATE','DELETE','TRUNCATE'])
def test_ps1_validation_immutable(api,db,validation_run,table,operation):
    statement=(f'UPDATE railplan.{table} SET created_at=clock_timestamp()' if operation=='UPDATE' else
               f'DELETE FROM railplan.{table}' if operation=='DELETE' else f'TRUNCATE railplan.{table} CASCADE')
    with pytest.raises(DBAPIError):
        with db.begin_nested(): db.execute(text(statement))

def test_ps1_validation_operator_isolation(api,db,validation_run):
    path,payload,result=validation_run
    other=db.execute(text("INSERT INTO railplan.operators(code,name) VALUES('V-OTHER','Other') RETURNING id")).scalar_one()
    dep=db.execute(text("INSERT INTO railplan.departments(operator_id,name) VALUES(:op,'Other') RETURNING id"),{'op':other}).scalar_one()
    user=db.execute(text("INSERT INTO railplan.users(department_id,auth_subject,display_name) VALUES(:d,'ps1-validator-other','Other') RETURNING id"),{'d':dep}).scalar_one()
    db.execute(text('INSERT INTO railplan.user_roles(user_id,role_id) VALUES(:u,:r)'),{'u':user,'r':uid('role/planner')})
    api.headers['X-Demo-User-Id']=str(user)
    assert api.get(path).status_code==404
    assert api.post(path,json=payload).status_code==404
    assert api.get('/api/ps1/validations/'+result['id']).status_code==404
    assert api.get('/api/ps1/validations/'+result['id']+'/violations').status_code==404

def test_ps1_validation_creator_and_operator_fk(api,db,validation_run):
    _,_,result=validation_run
    row=db.execute(text('SELECT created_by,operator_id FROM railplan.ps1_validation_runs WHERE id=:id'),{'id':result['id']}).mappings().one()
    assert row['created_by']==uid('planner')
    with pytest.raises(DBAPIError):
        with db.begin_nested():
            db.execute(text('''INSERT INTO railplan.ps1_validation_violations(validation_id,operator_id,ordinal,rule_code,evidence_snapshot)
                VALUES(:id,gen_random_uuid(),100,'schema','{}')'''),{'id':result['id']})

def test_ps1_validation_rollback(api,db,monkeypatch):
    from app.ps1 import load_files
    from app import repository
    from test_ps1_validation import sample_files
    iid=api.post('/api/ps1/instances',json={'files':load_files()}).json()['id']
    def fail(*args,**kwargs): raise RuntimeError('Injected event failure')
    monkeypatch.setattr(repository,'event',fail)
    with pytest.raises(RuntimeError):
        api.post(f'/api/ps1/instances/{iid}/validations',json={'scenario':'A','files':sample_files(),'idempotency_key':'rollback'})
    for table in ('ps1_validation_runs','ps1_validation_violations','ps1_validation_keys'):
        assert db.execute(text(f'SELECT count(*) FROM railplan.{table}')).scalar()==0

@pytest.mark.parametrize('role',['viewer','engineering_supervisor'])
def test_ps1_validation_requires_planner_or_admin(api,db,validation_run,role):
    path,payload,_=validation_run
    db.execute(text('DELETE FROM railplan.user_roles WHERE user_id=:u'),{'u':uid('planner')})
    db.execute(text('INSERT INTO railplan.user_roles(user_id,role_id) VALUES(:u,:r)'),{'u':uid('planner'),'r':uid('role/'+role)})
    assert api.post(path,json=payload).status_code==403

def test_seed_is_idempotent(db):
    seed(db)
    assert db.execute(text("SELECT count(*) FROM railplan.maintenance_requests")).scalar()==12

@pytest.mark.parametrize("query",["temporal_overlaps","sector_overlaps","team_double_booking","engineer_double_booking","equipment_double_booking","isolation_conflicts"])
def test_seeded_candidates(db,query):
    assert run(db,query,window_id=uid("window"))

def test_handback_is_warning_not_violation(db):
    assert not run(db,"dependency_violations",window_id=uid("window"))

def test_adjacent_ranges_do_not_overlap(db):
    assert not db.execute(text("SELECT tstzrange('2026-09-14 01:00+08','2026-09-14 02:00+08','[)') && tstzrange('2026-09-14 02:00+08','2026-09-14 03:00+08','[)')")).scalar()

def test_invalid_duration_rejected(db):
    with pytest.raises(DBAPIError):
        db.execute(text("UPDATE railplan.maintenance_requests SET min_duration_minutes=-1 WHERE id=:id"),{"id":uid("MR-018")})

def test_submitted_original_is_immutable(db):
    with pytest.raises(DBAPIError):
        db.execute(text("UPDATE railplan.maintenance_requests SET requested_start=requested_start+interval '5 minutes' WHERE id=:id"),{"id":uid("MR-018")})

def test_spatial_intersection(db):
    assert db.execute(text("SELECT ST_Intersects(ST_GeomFromText('POLYGON((0 0,2 0,2 2,0 2,0 0))',4326),ST_GeomFromText('POLYGON((1 1,3 1,3 3,1 3,1 1))',4326))")).scalar()

def test_qualification_and_expiry(db):
    params={"request_id":uid("MR-018"),"scenario_id":uid("scenario/minimum_disruption")}
    before=run(db,"available_qualified_engineers",**params)
    assert before
    db.execute(text("UPDATE railplan.engineer_skills SET ends_at='2026-09-14 00:00+08'"))
    assert not run(db,"available_qualified_engineers",**params)

def test_missing_skill(db):
    db.execute(text("DELETE FROM railplan.engineer_skills"))
    assert not run(db,"available_qualified_engineers",request_id=uid("MR-018"),scenario_id=uid("scenario/minimum_disruption"))

def test_audit_and_freeze(db):
    old=db.execute(text("SELECT count(*) FROM railplan.audit_logs")).scalar()
    db.execute(text("UPDATE railplan.maintenance_requests SET description='test' WHERE id=:id"),{"id":uid("MR-018")})
    assert db.execute(text("SELECT count(*) FROM railplan.audit_logs")).scalar()>old
    with pytest.raises(DBAPIError):
        db.execute(text("DELETE FROM railplan.audit_logs"))

def test_original_and_scenario_differ(db):
    rows=run(db,"compare_timings",scenario_id=uid("scenario/minimum_disruption"))
    assert any(r["request_code"]=="MR-024" and r["starts_at"]!=r["original_start"] for r in rows)

def test_pending_scenario_content_frozen(db):
    db.execute(text("UPDATE railplan.scenarios SET status='pending_review' WHERE id=:id"),{"id":uid("scenario/minimum_disruption")})
    with pytest.raises(DBAPIError):
        db.execute(text("UPDATE railplan.scenario_assignments SET reason='tampered' WHERE scenario_id=:id"),{"id":uid("scenario/minimum_disruption")})

def test_approval_immutability_trigger_exists(db):
    assert db.execute(text("""SELECT count(*) FROM pg_trigger WHERE tgrelid='railplan.schedule_versions'::regclass AND tgname IN ('immutable_row','immutable_table','schedule_guard')""")).scalar()==3

def test_command_centre(db):
    payload=run(db,"command_centre",window_id=uid("window"),scenario_id=None)[0]["payload"]
    assert len(payload["requests"])==12
    assert len(payload["scenarios"])==3
    assert len(payload["conflicts"])==5

def test_database_columns_match_models(db):
    for table in Base.metadata.tables.values():
        cols=db.execute(text("SELECT column_name FROM information_schema.columns WHERE table_schema='railplan' AND table_name=:t"),{"t":table.name}).scalars().all()
        assert set(cols)==set(table.c.keys())

@pytest.fixture
def scoring_api(api,db):
    from app.seed_scoring import seed_scoring
    seed_scoring(db)
    api.headers["X-Demo-User-Id"]=str(uid("scoring-admin"))
    cid=str(db.execute(text("SELECT id FROM railplan.conflicts ORDER BY id LIMIT 1")).scalar_one())
    return api,cid

def score_body(api,cid,key="scoring-test-key"):
    response=api.get(f"/api/conflicts/{cid}/scoring-context")
    assert response.status_code==200,response.text
    ctx=response.json()
    return {"policy_id":str(uid("scoring-policy/1")),"expected_conflict_version":ctx["version"],
            "expected_input_fingerprint":ctx["input_fingerprint"],"idempotency_key":key}

def test_score_persistence_and_duplicate_keys(scoring_api,db):
    api,cid=scoring_api;body=score_body(api,cid)
    first=api.post(f"/api/conflicts/{cid}/scores",json=body)
    assert first.status_code==200,first.text
    value=first.json()
    assert value["result"]["score_status"]=="partial"
    assert value["freshness"]=="fresh"
    assert api.post(f"/api/conflicts/{cid}/scores",json=body).json()["id"]==value["id"]
    body["idempotency_key"]="second-retry-key"
    assert api.post(f"/api/conflicts/{cid}/scores",json=body).json()["id"]==value["id"]
    assert db.execute(text("SELECT count(*) FROM railplan.conflict_scores")).scalar()==1
    assert api.get(f"/api/conflicts/{cid}/scores/latest").json()["id"]==value["id"]
    assert api.get(f"/api/conflicts/{cid}").json()["latest_score"]["id"]==value["id"]

def test_score_staleness_and_key_collision(scoring_api,db):
    api,cid=scoring_api;body=score_body(api,cid)
    first=api.post(f"/api/conflicts/{cid}/scores",json=body)
    assert first.status_code==200,first.text
    db.execute(text("""UPDATE railplan.maintenance_requests SET description=description||' updated'
      WHERE id=(SELECT request_id FROM railplan.conflict_requests WHERE conflict_id=:id ORDER BY request_id LIMIT 1)"""),{"id":cid})
    replay=api.post(f"/api/conflicts/{cid}/scores",json=body)
    assert replay.status_code==200 and replay.json()["freshness"]=="stale"
    body["expected_conflict_version"]+=1
    assert api.post(f"/api/conflicts/{cid}/scores",json=body).status_code==409
    body["idempotency_key"]="fresh-but-stale-input"
    assert api.post(f"/api/conflicts/{cid}/scores",json=body).status_code==409
    refreshed=score_body(api,cid,"fresh-input-key")
    assert api.post(f"/api/conflicts/{cid}/scores",json=refreshed).status_code==200
    assert api.get(f"/api/conflicts/{cid}/scores").json()["total"]==2

@pytest.mark.parametrize("table",["conflict_scores","scoring_policies","score_idempotency_keys"])
def test_score_and_policy_history_immutable(scoring_api,db,table):
    api,cid=scoring_api
    response=api.post(f"/api/conflicts/{cid}/scores",json=score_body(api,cid))
    assert response.status_code==200,response.text
    with pytest.raises(DBAPIError):
        with db.begin_nested():db.execute(text(f"DELETE FROM railplan.{table}"))

def test_policy_activation_and_duplicate_version(scoring_api,db):
    api,cid=scoring_api
    first=api.post("/api/scoring-policies",json={"version":2})
    assert first.status_code==201,first.text
    pid=first.json()["id"]
    assert api.post("/api/scoring-policies",json={"version":2}).status_code==409
    assert api.post(f"/api/scoring-policies/{pid}/activate").status_code==200
    assert api.post(f"/api/scoring-policies/{pid}/activate").status_code==200
    assert db.execute(text("SELECT count(*) FROM railplan.scoring_policy_activations WHERE ends_at IS NULL")).scalar()==1

def test_score_event_failure_rolls_back(scoring_api,db,monkeypatch):
    from app import repository
    api,cid=scoring_api;body=score_body(api,cid)
    def fail(*args,**kwargs):raise RuntimeError("injected activity failure")
    monkeypatch.setattr(repository,"event",fail)
    # TestClient propagates server exceptions; session dependency must roll back.
    with pytest.raises(RuntimeError):api.post(f"/api/conflicts/{cid}/scores",json=body)
    assert db.execute(text("SELECT count(*) FROM railplan.conflict_scores")).scalar()==0

def test_lock_snapshot_and_history(db):
    from sqlalchemy.orm import Session
    from app.services import create_lock
    from app.schemas import LockCreate
    with Session(bind=db,join_transaction_mode="create_savepoint") as session:
        actor=session.execute(text("SELECT * FROM railplan.users WHERE id=:id"),{"id":uid("planner")}).mappings().one()
        result=create_lock(session,uid("MR-018"),LockCreate(expected_version=1,reason="Test fixed timing"),actor)
        assert result["status"]=="locked"
        values=session.execute(text("SELECT locked_values FROM railplan.request_locks WHERE id=:id"),{"id":result["id"]}).scalar_one()
        assert values["starts_at"]
        session.rollback()

@pytest.fixture
def api(db,monkeypatch):
    from sqlalchemy.orm import Session
    from fastapi.testclient import TestClient
    from app.main import app
    from app.database import session
    monkeypatch.setenv("RAILPLAN_DEMO_AUTH","1")
    monkeypatch.setenv("RAILPLAN_ENV","development")
    def transaction_session():
        with Session(bind=db,join_transaction_mode="create_savepoint") as s:
            with s.begin():yield s
    app.dependency_overrides[session]=transaction_session
    from app.routers.ps1_optimisation import optimisation_session_factory
    app.dependency_overrides[optimisation_session_factory]=lambda:lambda:Session(bind=db,join_transaction_mode='create_savepoint')
    try:
        with TestClient(app) as client:
            client.headers["X-Demo-User-Id"]=str(uid("planner"))
            yield client
    finally:app.dependency_overrides.clear()

def draft_payload():
    return {"submit":False,"window_id":str(uid("window")),"work_type_id":str(uid("type/Signal inspection")),
      "title":"API inspection","description":"Integration test","requested_start":"2026-09-14T01:00:00+08:00",
      "requested_end":"2026-09-14T02:00:00+08:00","earliest_start":"2026-09-14T00:30:00+08:00",
      "latest_finish":"2026-09-14T04:30:00+08:00","min_duration_minutes":30,"max_duration_minutes":90,
      "sector_ids":[str(uid("sector/Bishan–Braddell"))],"team_ids":[str(uid("team/Team Alpha"))]}

def test_api_request_lifecycle(api):
    response=api.post("/api/maintenance-requests",json=draft_payload())
    assert response.status_code==201,response.text
    rid=response.json()["id"]
    response=api.patch("/api/maintenance-requests/"+rid,json={"expected_version":1,"title":"Updated title"})
    assert response.status_code==200,response.text
    assert response.json()["version"]==2
    assert api.patch("/api/maintenance-requests/"+rid,json={"expected_version":1,"title":"Stale"}).status_code==409
    submitted=api.post("/api/maintenance-requests/"+rid+"/submit",json={"expected_version":2})
    assert submitted.status_code==200,submitted.text
    assert api.patch("/api/maintenance-requests/"+rid,json={"expected_version":3,"title":"Not allowed"}).status_code==409
    assert api.post("/api/maintenance-requests/"+rid+"/cancel",json={"expected_version":3,"reason":"No longer required"}).status_code==200
    assert api.get("/api/maintenance-requests/"+rid).json()["status_code"]=="cancelled"
    timeline=api.get("/api/timeline/"+str(uid("window")))
    assert timeline.status_code==200,timeline.text
    assert rid not in [x["request_id"] for x in timeline.json()]

def test_api_scenario_preview_edit_lock_release(api):
    created=api.post("/api/scenarios",json={"window_id":str(uid("window")),
      "objective_id":str(uid("objective/minimum_disruption")),"name":"Editable baseline"})
    assert created.status_code==201,created.text
    sid=created.json()["id"]
    data=api.get("/api/scenarios/"+sid).json()
    assignment=next(a for a in data["assignments"] if a["request_id"]==str(uid("MR-018")))
    edit={"expected_version":data["summary"]["version"],"starts_at":"2026-09-14T01:00:00+08:00",
          "ends_at":"2026-09-14T02:00:00+08:00","reason":"Move 15 minutes"}
    path="/api/scenarios/"+sid+"/assignments/"+assignment["id"]
    preview=api.post(path+"/preview",json=edit)
    assert preview.status_code==200,preview.text
    assert preview.json()["basic_valid"] and not preview.json()["complete_conflict_validation_performed"]
    assert api.get("/api/scenarios/"+sid).json()["summary"]["version"]==edit["expected_version"]
    lock=api.post("/api/maintenance-requests/"+str(uid("MR-018"))+"/locks",json={
      "expected_version":1,"scenario_id":sid,"reason":"Keep time","fields":["timing"]})
    assert lock.status_code==201,lock.text
    assert api.patch(path,json=edit).status_code==409
    release=api.post("/api/locks/"+lock.json()["id"]+"/release",json={"reason":"Allow move"})
    assert release.status_code==200,release.text
    response=api.patch(path,json=edit)
    assert response.status_code==200,response.text
    assert response.json()["validation_status"]=="unvalidated"
    assert api.get("/api/maintenance-requests/"+str(uid("MR-018"))).json()["requested_start"].startswith("2026-09-13T16:45") or api.get("/api/maintenance-requests/"+str(uid("MR-018"))).json()["requested_start"].startswith("2026-09-14T00:45")

def test_api_unknown_geometry_and_availability(api,db):
    geo=api.get("/api/network/stations")
    assert geo.status_code==200,geo.text
    assert all(x["geometry"] is None and x["geometry_available"] is False for x in geo.json()["items"])
    db.execute(text("DELETE FROM railplan.engineer_availability"))
    response=api.get("/api/resources/availability",params={"resource_type":"engineer",
      "starts_at":"2026-09-14T01:00:00+08:00","ends_at":"2026-09-14T02:00:00+08:00"})
    assert response.status_code==200,response.text
    assert all(x["availability"]=="unknown" for x in response.json()["items"])

def test_api_activity_read_is_per_user(api,db):
    events=api.get("/api/activity").json()["items"]
    assert events
    result=api.post("/api/activity/read",json={"event_ids":[events[0]["id"]]})
    assert result.status_code==200,result.text
    assert db.execute(text("SELECT count(*) FROM railplan.activity_events")).scalar()>0
    assert db.execute(text("SELECT count(*) FROM railplan.event_reads")).scalar()==1

def test_api_foreign_key_failure_rolls_back(api,db):
    from uuid import uuid4
    count=db.execute(text("SELECT count(*) FROM railplan.maintenance_requests")).scalar()
    payload=draft_payload();payload["team_ids"]=[str(uuid4())]
    assert api.post("/api/maintenance-requests",json=payload).status_code==422
    assert db.execute(text("SELECT count(*) FROM railplan.maintenance_requests")).scalar()==count

def test_api_operator_isolation(api,db):
    # Ownership check uses the actor's operator, not UUID obscurity.
    other=db.execute(text("INSERT INTO railplan.operators(code,name) VALUES('OTHER','Other operator') RETURNING id")).scalar_one()
    dep=db.execute(text("INSERT INTO railplan.departments(operator_id,name) VALUES(:op,'Other') RETURNING id"),{"op":other}).scalar_one()
    u=db.execute(text("INSERT INTO railplan.users(department_id,auth_subject,display_name) VALUES(:d,'other','Other') RETURNING id"),{"d":dep}).scalar_one()
    db.execute(text("INSERT INTO railplan.user_roles(user_id,role_id) VALUES(:u,:r)"),{"u":u,"r":uid("role/viewer")})
    api.headers["X-Demo-User-Id"]=str(u)
    assert api.get("/api/maintenance-requests/"+str(uid("MR-018"))).status_code==404
    assert api.get("/api/engineering-windows").json()["items"]==[]


def test_detect_persist_and_score_through_api(api, db):
    """All four backend features exercised together on PostgreSQL/PostGIS."""
    from app.seed_scoring import seed_scoring
    seed_scoring(db)
    response=api.post("/api/analyses",json={"window_id":str(uid("window"))})
    assert response.status_code==201,response.text
    result=response.json()
    assert result["status"]=="completed",result
    assert result["conflict_count"]>0
    rows=api.get(f"/api/analyses/{result['id']}/conflicts").json()
    assert len(rows)==result["conflict_count"]
    assert all(row["detection_method"]=="automatic" for row in rows)
    cid=rows[0]["id"]
    api.headers["X-Demo-User-Id"]=str(uid("scoring-admin"))
    response=api.post(f"/api/conflicts/{cid}/scores",json=score_body(api,cid,"merged-flow-score"))
    assert response.status_code==200,response.text
    assert len(response.json()["result"]["components"])==5
    assert api.get(f"/api/conflicts/{cid}/scores/latest").json()["id"]==response.json()["id"]
    assert db.execute(text("SELECT count(*) FROM railplan.conflict_scores WHERE conflict_id=:id"),{"id":cid}).scalar()==1
