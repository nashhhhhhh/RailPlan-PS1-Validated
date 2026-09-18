from pathlib import Path
import re
import pytest
from pglast import parse_sql
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable
from app.models import Base
from app.queries import QUERIES
from app.schemas import RequestCreate
from app.main import app
from app.seed import seed
from fastapi.testclient import TestClient

ROOT=Path(__file__).resolve().parents[1]

@pytest.mark.parametrize("path",sorted((ROOT/"sql").glob("*.sql")),ids=lambda p:p.name)
def test_postgres_sql_parses(path):
    assert parse_sql(path.read_text())

@pytest.mark.parametrize("name",list(QUERIES))
def test_query_parses(name):
    # PostgreSQL parser parameters: :name -> $n; do not rewrite :: casts.
    names={}
    def param(m):
        names.setdefault(m[1],len(names)+1)
        return "$"+str(names[m[1]])
    assert parse_sql(re.sub(r"(?<!:):([a-zA-Z_]\w*)",param,QUERIES[name]))

def test_models_compile():
    assert len(Base.metadata.tables)==102
    for t in Base.metadata.sorted_tables:
        assert str(CreateTable(t).compile(dialect=postgresql.dialect()))

def test_migration_uses_all_assets(monkeypatch):
    import importlib
    revision=importlib.import_module("migrations.versions.0001_initial")
    calls=[]
    class Connection:
        def exec_driver_sql(self,sql,**options):
            assert options["execution_options"]["no_parameters"] is True
            assert parse_sql(sql)
            calls.append(sql)
    monkeypatch.setattr(revision.op,"get_bind",lambda:Connection())
    revision.upgrade()
    assert len(calls)==3
    assert "CREATE TABLE maintenance_requests" in calls[0]
    assert "CREATE FUNCTION" in calls[1]
    assert "CREATE VIEW" in calls[2]
    with pytest.raises(RuntimeError):
        revision.downgrade()

def test_schema_model_columns_agree():
    sql=(ROOT/"sql/001_schema.sql").read_text()+"\n"+(ROOT/"sql/005_scoring.sql").read_text().replace("CREATE TABLE railplan.","CREATE TABLE ")+"\n"+(ROOT/"sql/008_ps1_instances.sql").read_text().replace("CREATE TABLE railplan.","CREATE TABLE ")
    sql+='\n'+(ROOT/'sql/009_ps1_validations.sql').read_text().replace('CREATE TABLE railplan.','CREATE TABLE ')
    sql+='\n'+(ROOT/'sql/010_ps1_optimisation_runs.sql').read_text().replace('CREATE TABLE railplan.','CREATE TABLE ')
    for table in Base.metadata.tables.values():
        body=re.search(r"CREATE TABLE "+table.name+r" \((.*?)\n\);",sql,re.S)[1]
        columns=[line.strip().split()[0] for line in body.splitlines()
                 if line.strip() and not line.strip().startswith(("CHECK","UNIQUE","FOREIGN","PRIMARY"))]
        additions={"conflicts":{"version"},"scoring_policies":{"operator_id","definition"}}
        assert set(columns)|additions.get(table.name,set())==set(table.c.keys())

def sample():
    from uuid import uuid4
    return dict(window_id=uuid4(),work_type_id=uuid4(),title="Inspection",
      requested_start="2026-09-14T01:00:00+08:00",requested_end="2026-09-14T02:00:00+08:00",
      earliest_start="2026-09-14T00:30:00+08:00",latest_finish="2026-09-14T04:30:00+08:00",
      min_duration_minutes=30,max_duration_minutes=90,sector_ids=[uuid4()])

def test_valid_request():
    assert RequestCreate(**sample()).title=="Inspection"

@pytest.mark.parametrize("change",[
 {"requested_end":"2026-09-14T00:00:00+08:00"},
 {"requested_start":"2026-09-14T01:00:00"},
 {"title":"   "},{"min_duration_minutes":0},{"max_duration_minutes":40},
 {"earliest_start":"2026-09-14T01:30:00+08:00"},{"sector_ids":[]},
 {"latest_finish":"2026-09-14T01:30:00+08:00"},
 {"unexpected_ui_colour":"red"},
])
def test_invalid_request(change):
    data=sample();data.update(change)
    with pytest.raises(ValueError):
        RequestCreate(**data)

def test_duplicate_relations_rejected():
    data=sample();data["sector_ids"]*=2
    with pytest.raises(ValueError):
        RequestCreate(**data)

def test_seed_fixture_references():
    class Result:
        def scalar(self): return None
    class Recorder:
        def __init__(self): self.rows=[]
        def execute(self,statement,params):
            match=re.search(r"INSERT INTO railplan\.(\w+)",str(statement))
            if match: self.rows.append((match[1],params))
            return Result()
    db=Recorder()
    seed(db)
    known={}
    for table,values in db.rows:
        known.setdefault(table,set()).add(values["id"])
    assert len(known["maintenance_requests"])==12
    assert len(known["stations"])==8
    assert len(known["scenario_assignments"])==36
    assert len(known["conflicts"])==5
    for table,values in db.rows:
        model=Base.metadata.tables["railplan."+table]
        for column in model.c:
            if column.name not in values or values[column.name] is None:
                continue
            for fk in column.foreign_keys:
                if fk.column.name=="id":
                    assert values[column.name] in known[fk.column.table.name],(table,column.name)
    scenarios=[v for t,v in db.rows if t=="scenarios"]
    assert all(v["provenance"]=="ui_preset" for v in scenarios)
    assignments=[v for t,v in db.rows if t=="scenario_assignments"]
    assert all(not v["feasible"] for v in assignments)

def test_openapi_and_health():
    with TestClient(app) as client:
        assert client.get("/health").json()["operational_approval_available"] is False
        schema=client.get("/openapi.json").json()
        assert "/api/maintenance-requests" in schema["paths"]
        assert "/api/ps1/optimise/scenario-b/preview" in schema["paths"]
        assert client.get("/health").json()["scenario_b_solver_available"] is True

def test_scoring_trigger_prefixes_are_literal_and_scenarios_not_duplicated():
    sql=(ROOT/'sql/005_scoring.sql').read_text()
    assert "left(tablename,8)='request_'" in sql
    assert "left(tablename,9)='scenario_'" in sql
    assert "tablename LIKE 'scenario_%'" not in sql
    # scenarios is explicitly listed; literal scenario_ only matches names with the underscore prefix.
    assert "'scenario_assignments','scenarios'" in sql

def test_scenario_b_migration_is_additive_and_refuses_downgrade():
    import importlib
    revision=importlib.import_module('migrations.versions.0008_ps1_scenario_b')
    assert revision.down_revision=='0007'
    with pytest.raises(RuntimeError,match='Archive sealed Scenario B'):revision.downgrade()

def test_default_auth_fails_closed(monkeypatch):
    from app.database import session
    monkeypatch.delenv("RAILPLAN_DEMO_AUTH",raising=False)
    def fake_db(): yield None
    app.dependency_overrides[session]=fake_db
    try:
        with TestClient(app) as client:
            assert client.get("/api/timeline/00000000-0000-0000-0000-000000000001").status_code==503
    finally:
        app.dependency_overrides.clear()
