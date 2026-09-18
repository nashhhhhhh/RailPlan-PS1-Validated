from datetime import datetime,timedelta,timezone
from uuid import uuid4
import importlib,re
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pglast import parse_sql
from app.main import app
from app.database import session
from app.dependencies import identity
from app.contracts import AssignmentEdit,RequestPatch
from app.routers.scenarios import basic_issues
from app.routers.network import bbox_values
from app import repository as repo

@pytest.fixture
def client():
    actor={"id":uuid4(),"department_id":uuid4(),"operator_id":uuid4(),"roles":{"planner"}}
    def db():yield None
    app.dependency_overrides[session]=db
    app.dependency_overrides[identity]=lambda:actor
    with TestClient(app,raise_server_exceptions=False) as value:
        yield value,actor
    app.dependency_overrides.clear()

def test_static_compare_route_precedes_uuid_route(client,monkeypatch):
    c,actor=client;sid1=uuid4();sid2=uuid4();wid=uuid4()
    monkeypatch.setattr(repo,"scenario",lambda *a,**k:{"window_id":wid})
    from app.routers import scenarios
    monkeypatch.setattr(scenarios,"summary",lambda db,id:{"id":id,"name":"Draft","status":"draft","version":1,"validation_status":"unvalidated","provenance":"manual"})
    response=c.get("/api/scenarios/compare",params=[("ids",str(sid1)),("ids",str(sid2))])
    assert response.status_code==200
    assert response.json()["conflict_resolution_comparable"] is False

@pytest.mark.parametrize("path,params",[
 ("/api/maintenance-requests",{"limit":0}),
 ("/api/maintenance-requests",{"limit":201}),
 ("/api/maintenance-requests",{"offset":-1}),
 ("/api/maintenance-requests",{"sort":"id;DROP TABLE users"}),
 ("/api/maintenance-requests",{"priority":"unknown"}),
 ("/api/engineering-windows",{"limit":9999}),
 ("/api/scenarios/compare",{"ids":"not-a-uuid"}),
])
def test_invalid_filters_are_structured(client,path,params):
    response=client[0].get(path,params=params)
    assert response.status_code==422
    assert response.json()["error"]["code"]=="INVALID_INPUT"
    assert response.json()["error"]["fields"]
    assert response.headers["X-Correlation-Id"]==response.json()["error"]["correlation_id"]

def test_planner_cannot_create_policy_or_score(client):
    c,_=client
    assert c.post("/api/scoring-policies",json={}).status_code==403
    assert c.post("/api/conflicts/"+str(uuid4())+"/scores",json={
      "policy_id":str(uuid4()),"expected_conflict_version":1,
      "expected_input_fingerprint":"a"*64,"idempotency_key":"test-key"}).status_code==403

def test_scoring_rejects_missing_concurrency_token(client):
    response=client[0].post("/api/conflicts/"+str(uuid4())+"/scores",json={
      "policy_id":str(uuid4()),"expected_conflict_version":1,"idempotency_key":"test-key"})
    assert response.status_code==422

@pytest.mark.parametrize("path,body",[
 ("/api/optimisation-runs",lambda w:{"window_id":str(w),"objective_id":str(uuid4())}),
])
def test_missing_workers_reject_without_accepting(client,monkeypatch,path,body):
    monkeypatch.setattr(repo,"window",lambda *a,**k:{})
    response=client[0].post(path,json=body(uuid4()))
    assert response.status_code==503
    assert "no job was accepted" in response.json()["error"]["message"]

def test_approval_disabled(client,monkeypatch):
    monkeypatch.setattr(repo,"scenario",lambda *a,**k:{"version":2})
    response=client[0].post("/api/scenarios/"+str(uuid4())+"/approval",
        json={"workflow_id":str(uuid4()),"expected_version":2})
    assert response.status_code==501

def test_capabilities_do_not_invent_engines(client):
    value=client[0].get("/api/capabilities").json()
    assert value["conflict_analysis_available"]
    assert not value["optimisation_available"]
    assert not value["copilot_available"]
    assert not value["operational_approval_available"]

def test_unauthorized_role(client):
    client[1]["roles"]={"viewer"}
    response=client[0].post("/api/analyses",json={"window_id":str(uuid4())})
    assert response.status_code==403

def test_stale_version():
    with pytest.raises(HTTPException) as error:repo.version({"version":3},2)
    assert error.value.status_code==409

@pytest.mark.parametrize("bbox",["1,2,3","nan,1,2,3","1,5,2,4","181,0,182,1","x,y,z,w","170,-5,-170,5"])
def test_bad_bbox(bbox):
    with pytest.raises(HTTPException):bbox_values(bbox)

def test_valid_bbox():
    assert bbox_values("103,1,104,2")==[103,1,104,2]
    assert bbox_values(None) is None

def sample():
    start=datetime(2026,9,14,0,30,tzinfo=timezone(timedelta(hours=8)))
    r={"min_duration_minutes":30,"max_duration_minutes":90,"earliest_start":start,"latest_finish":start+timedelta(hours=4),"version":2,"status_code":"submitted"}
    w={"starts_at":start,"ends_at":start+timedelta(hours=4)}
    a={"request_version":2}
    s={"status":"draft"}
    p=AssignmentEdit(expected_version=1,starts_at=start+timedelta(minutes=30),ends_at=start+timedelta(minutes=90),reason="Reposition")
    return r,w,a,s,p

def test_valid_preview_is_only_basic():
    r,w,a,s,p=sample()
    assert not basic_issues(r,w,a,s,p,[])

@pytest.mark.parametrize("change,expected",[
 ("cancelled","no longer"),("stale","stale"),("review","draft"),("duration","Duration"),("outside","outside")])
def test_preview_rejects_invalid_states(change,expected):
    r,w,a,s,p=sample()
    if change=="cancelled":r["status_code"]="cancelled"
    elif change=="stale":a["request_version"]=1
    elif change=="review":s["status"]="pending_review"
    elif change=="duration":r["max_duration_minutes"]=45
    elif change=="outside":w["ends_at"]=p.starts_at
    assert any(expected in issue for issue in basic_issues(r,w,a,s,p,[]))

def test_timing_lock():
    r,w,a,s,p=sample()
    lock={"fields":["timing"],"locked_values":{"starts_at":p.starts_at.isoformat(),"ends_at":p.ends_at.isoformat()}}
    assert not basic_issues(r,w,a,s,p,[lock])
    p.starts_at+=timedelta(minutes=5)
    assert "Timing is locked" in basic_issues(r,w,a,s,p,[lock])

@pytest.mark.parametrize("field,key,stored",[("team","team_ids","teams"),("engineers","engineer_ids","engineers"),
 ("equipment","asset_ids","equipment"),("sectors","sector_ids","sectors")])
def test_resource_locks(field,key,stored):
    r,w,a,s,p=sample()
    setattr(p,key,[uuid4()])
    lock={"fields":[field],"locked_values":{stored:[str(uuid4())]}}
    assert field+" is locked" in basic_issues(r,w,a,s,p,[lock])

def test_cross_midnight_duration():
    p=AssignmentEdit(expected_version=1,starts_at="2026-09-14T23:45:00+08:00",
                     ends_at="2026-09-15T00:45:00+08:00",reason="Overnight")
    assert (p.ends_at-p.starts_at).total_seconds()==3600

@pytest.mark.parametrize("values",[{"title":None},{"title":"  "},{"sector_ids":[]},{"description":None},{}])
def test_invalid_request_patch(values):
    with pytest.raises(ValueError):RequestPatch(expected_version=1,**values)

def test_second_migration_parses(monkeypatch):
    module=importlib.import_module("migrations.versions.0002_api_support")
    class Conn:
        def exec_driver_sql(self,sql,**kw):
            assert parse_sql(sql)
    monkeypatch.setattr(module.op,"get_bind",lambda:Conn())
    module.upgrade();module.downgrade()

def test_readiness_does_not_leak_credentials(client,monkeypatch):
    import app.main as main
    def broken():raise RuntimeError("postgresql://secret-password")
    monkeypatch.setattr(main,"engine",broken)
    response=client[0].get("/health/ready")
    assert response.status_code==503 and "secret-password" not in response.text

def test_cors_rejects_unconfigured_origin(client):
    response=client[0].options("/api/maintenance-requests",headers={
      "Origin":"https://untrusted.example","Access-Control-Request-Method":"POST"})
    assert response.status_code==400
    assert "access-control-allow-origin" not in response.headers

@pytest.mark.parametrize("path,params",[
 ("/api/network/stations",{"bbox":"103,1,104,2"}),
 ("/api/network/sectors",{}),
 ("/api/workzones",{}),
 ("/api/teams",{"search":"Alpha"}),
 ("/api/engineers",{}),
 ("/api/equipment",{}),
 ("/api/resources/availability",{"resource_type":"engineer","starts_at":"2026-09-14T01:00:00+08:00","ends_at":"2026-09-14T02:00:00+08:00"}),
 ("/api/resources/availability",{"resource_type":"team","starts_at":"2026-09-14T01:00:00+08:00","ends_at":"2026-09-14T02:00:00+08:00"}),
 ("/api/resources/availability",{"resource_type":"equipment","starts_at":"2026-09-14T01:00:00+08:00","ends_at":"2026-09-14T02:00:00+08:00"}),
 ("/api/maintenance-requests",{"search":"';DROP TABLE users;--","sort":"updated"}),
 ("/api/activity",{}),
])
def test_generated_read_sql_parses_and_binds(client,monkeypatch,path,params):
    queries=[]
    def page(db,sql,bound,limit,offset):
        names={}
        def parameter(match):
            assert match[1] in bound
            names.setdefault(match[1],len(names)+1)
            return "$"+str(names[match[1]])
        parsed=re.sub(r"(?<!:):([a-zA-Z_]\w*)",parameter,sql)
        assert parse_sql(parsed)
        assert "DROP TABLE" not in sql
        queries.append(sql)
        return {"items":[],"limit":limit,"offset":offset,"total":0}
    monkeypatch.setattr(repo,"page",page)
    response=client[0].get(path,params=params)
    assert response.status_code==200,response.text
    assert queries

def test_fixed_request_cannot_move_without_a_lock_record():
    r,w,a,s,p=sample()
    r.update(flexibility="fixed",requested_start=p.starts_at,requested_end=p.ends_at)
    assert not basic_issues(r,w,a,s,p,[])
    p.starts_at+=timedelta(minutes=5)
    assert "Requested timing is fixed" in basic_issues(r,w,a,s,p,[])

def test_unknown_path_uses_standard_error(client):
    response=client[0].get("/api/does-not-exist")
    assert response.status_code==404
    assert response.json()["error"]["code"]=="NOT_FOUND"
    assert response.json()["error"]["correlation_id"]==response.headers["X-Correlation-Id"]

def test_method_error_preserves_allow_header(client):
    response=client[0].delete("/api/capabilities")
    assert response.status_code==405
    assert "GET" in response.headers["allow"]
    assert response.json()["error"]["message"]=="Method Not Allowed"
    assert response.json()["error"]["code"]=="METHOD_NOT_ALLOWED"
