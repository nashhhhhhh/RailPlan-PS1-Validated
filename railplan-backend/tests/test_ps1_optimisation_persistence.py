"""Pure fingerprint/export/metric and HTTP-boundary tests, not database guarantees."""
import copy
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.exc import DBAPIError
from app.main import app
from app.database import session
from app.dependencies import identity
from app.ps1_validation.submission import fingerprint
from app.ps1_optimisation.contracts import OptimiseInput,OptimiseResult
from app.ps1_optimisation.saved_contracts import SavedOptimiseInput,SavedOptimiseResult
from app.ps1_optimisation import persistence as store
from app.ps1_optimisation.exporter import export,export_bundle
from app.ps1_optimisation.preprocessing import prepare,InputError
from app.ps1_optimisation.service import optimise
from app.routers import ps1_optimisation as router
from test_ps1_optimisation import small,lock

@pytest.fixture
def instance():return {'id':uuid4(),'dataset':small()}

@pytest.fixture
def accepted_result(instance):return optimise(instance['dataset'],OptimiseInput(time_limit_seconds=5.0))

def digest(instance,options=None,baseline=None):
    return fingerprint(store.effective_configuration(instance,options or OptimiseInput(),baseline))

def test_defaults_and_sorted_placements_fingerprint(instance):
    assert digest(instance)==digest(instance,OptimiseInput(time_limit_seconds=20.0,random_seed=0))
    a=OptimiseInput(locked_placements=[lock('B'),lock('A')],baseline_placements=[lock('B'),lock('A')])
    b=OptimiseInput(locked_placements=list(reversed(a.locked_placements)),baseline_placements=list(reversed(a.baseline_placements)))
    assert digest(instance,a)==digest(instance,b)
    b=b.model_copy(deep=True); b.locked_placements[0].access_night=1
    assert digest(instance,a)!=digest(instance,b)

@pytest.mark.parametrize('field,value',[('time_limit_seconds',10.0),('deterministic_time_limit',1.0),('random_seed',3),('physical_nights_per_week',6)])
def test_effective_options_change_fingerprint(instance,field,value):
    assert digest(instance)!=digest(instance,OptimiseInput(**{field:value}))

def test_identity_and_version_fingerprint(instance,monkeypatch):
    original=digest(instance)
    changed={**instance,'id':uuid4()};assert digest(changed)!=original
    assert digest(instance,baseline=uuid4())!=original
    changed=copy.deepcopy(instance);changed['dataset']['fingerprint']='a'*64
    assert digest(changed)!=original
    monkeypatch.setattr(store,'OBJECTIVE_POLICY','new-policy')
    assert digest(instance)!=original

def test_persistence_fields_excluded_from_pure_options(instance):
    a=SavedOptimiseInput(idempotency_key='first'); b=SavedOptimiseInput(idempotency_key='second')
    assert store.resolve(None,{},instance,a)==store.resolve(None,{},instance,b)
    with pytest.raises(ValidationError):OptimiseInput(idempotency_key='not-a-solver-field')
    assert SavedOptimiseInput.model_validate({'baseline_run_id':str(uuid4())}).baseline_run_id
    pure=app.openapi()['components']['schemas']['OptimiseInput']['properties']
    assert 'locked_placements' in pure and 'baseline_run_id' not in pure and 'idempotency_key' not in pure

@pytest.mark.parametrize('key',['','a b','\t','x'*129])
def test_bad_keys(key):
    with pytest.raises(ValidationError):SavedOptimiseInput(idempotency_key=key)

def test_baseline_ambiguity():
    with pytest.raises(ValidationError):SavedOptimiseInput(baseline_run_id=uuid4(),baseline_placements=[lock('T0')])

def test_baseline_resolution_scope_and_placements(instance,monkeypatch):
    actor={'operator_id':uuid4()};run_id=uuid4();calls=[]
    def lookup(db,who,rid,iid):
        calls.append((who,rid,iid));return {'id':rid,'publishable':True}
    monkeypatch.setattr(store,'get_run',lookup)
    class DB:
        def execute(self,sql,params):
            assert params['op']==actor['operator_id'] and params['instance']==instance['id']
            return self
        def mappings(self):return [lock('T0',week=2,night=6,local=1).model_dump()]
    options=store.resolve(DB(),actor,instance,SavedOptimiseInput(baseline_run_id=run_id))
    assert options.baseline_placements==[lock('T0',week=2,night=6,local=1)]
    assert not options.locked_placements and calls==[(actor,run_id,instance['id'])]
    monkeypatch.setattr(store,'get_run',lambda *args:{'id':run_id,'publishable':False})
    with pytest.raises(HTTPException) as exc:store.resolve(DB(),actor,instance,SavedOptimiseInput(baseline_run_id=run_id))
    assert exc.value.status_code==422

def test_invalid_placement_checked_even_model_limited(instance):
    instance['dataset']['parameters']['horizon_weeks']=520
    instance['dataset']['tables']['activity_details']*=201
    with pytest.raises(InputError):store.resolve(None,{},instance,SavedOptimiseInput(locked_placements=[lock('UNKNOWN')]))

def test_export_wrapper_and_structured_records_agree(instance,accepted_result):
    options=OptimiseInput();data=prepare(instance['dataset'],options)
    bundle=export_bundle(instance['dataset'],data,accepted_result.physical_nights)
    assert export(instance['dataset'],data,accepted_result.physical_nights)==(bundle.files,bundle.physical_nights)
    records=store.schedule_records(instance,options,accepted_result)
    assert records['accesses'][0]['physical_night']==accepted_result.physical_nights[0].physical_night
    assert records['accesses'][0]['access_night']==accepted_result.physical_nights[0].access_night
    assert records['occupancies']==bundle.occupancies
    assert records['contract_results'][0]['weighted_overrun'] is None
    assert records['contract_results'][0]['overrun_days']==bundle.contract_results[0]['overrun_days']
    accepted_result.submission_files['RESULTS.csv']+='\n'
    with pytest.raises(RuntimeError):store.schedule_records(instance,options,accepted_result)

def test_lock_baseline_metadata(instance,accepted_result):
    options=OptimiseInput(locked_placements=[lock('T0')],baseline_placements=[lock('T0',week=2,night=5)])
    row=store.schedule_records(instance,options,accepted_result)['accesses'][0]
    assert row['locked'] and row['baseline_week']==2 and row['baseline_physical_night']==5

def test_primary_bound_uses_primary_stage_and_exact_units(accepted_result):
    accepted_result.validation_report.objective_score='48.30'
    accepted_result.stages=[{'name':'weighted_overrun_scaled_10','status':'FEASIBLE','best_bound':252.0},
        {'name':'raw_contract_overrun_days','status':'OPTIMAL','best_bound':9999}]
    score,bound,gap=store.primary_metrics(accepted_result,True)
    assert score==Decimal('48.30') and bound==Decimal('25.2')
    assert gap==((score-bound)/score).quantize(Decimal('0.000000000001'))
    accepted_result.stages=accepted_result.stages[1:]
    assert store.primary_metrics(accepted_result,True)==(score,None,None)

@pytest.mark.parametrize('bound',['NaN','Infinity','oops',-1,999999])
def test_invalid_bounds_are_not_invented(accepted_result,bound):
    accepted_result.stages=[{'name':'weighted_overrun_scaled_10','status':'FEASIBLE','best_bound':bound}]
    assert store.primary_metrics(accepted_result,True)[1:]==(None,None)

@pytest.mark.parametrize('status',list(store.OUTCOMES))
def test_outcome_mapping_does_not_conflate(status,instance):
    result=OptimiseResult(solver_status=status,solve_time_seconds=0,settings={})
    assert not store.accepted(result)
    assert store.schedule_records(instance,OptimiseInput(),result)=={'accesses':[],'occupancies':[],'contract_results':[]}
    assert store.OUTCOMES[status]==('bounded' if status=='UNKNOWN' else status.lower())

@pytest.fixture
def boundary(monkeypatch,instance):
    state={'active':0,'commits':0,'solves':0,'saved':[],'commit_failure':False}
    actor={'id':uuid4(),'operator_id':uuid4(),'roles':{'planner'}}
    class Boundary:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        @contextmanager
        def begin(self):
            state['active']+=1
            try:
                yield
                if state['commit_failure'] and state['saved']:raise DBAPIError('commit',{},Exception('commit failed'))
                state['commits']+=1
            finally:state['active']-=1
    app.dependency_overrides[router.optimisation_session_factory]=lambda:Boundary
    app.dependency_overrides[session]=lambda:object()
    app.dependency_overrides[identity]=lambda:actor
    monkeypatch.setattr(router,'identity',lambda *args:actor)
    monkeypatch.setattr(router,'get_instance',lambda *args:instance)
    monkeypatch.setattr(store,'existing_key',lambda *args,**kwargs:None)
    def solve(dataset,options):
        assert state['active']==0;state['solves']+=1
        return optimise(dataset,options)
    monkeypatch.setattr(router,'optimise',solve)
    def persist(db,actor,inst,payload,config,digest,result,records,start,end):
        assert state['active']==1 and end>=start
        state['saved'].append((result,records))
        return SavedOptimiseResult(**result.model_dump(),run_id=uuid4(),created=True,reused=False,
            created_at=datetime.now(timezone.utc),terminal_outcome=store.OUTCOMES[result.solver_status],input_fingerprint=digest)
    monkeypatch.setattr(store,'persist',persist)
    with TestClient(app,raise_server_exceptions=False) as client:yield client,state,actor
    app.dependency_overrides.clear()

def test_solve_outside_transactions_and_commit_before_success(boundary,instance):
    client,state,actor=boundary
    response=client.post(f'/api/ps1/instances/{instance["id"]}/optimise/scenario-a',json={})
    assert response.status_code==200,response.text
    assert response.json()['created'] and response.json()['publishable']
    assert state['commits']==2 and state['active']==0 and state['solves']==1

def test_commit_failure_never_returns_saved_success(boundary,instance):
    client,state,actor=boundary;state['commit_failure']=True
    response=client.post(f'/api/ps1/instances/{instance["id"]}/optimise/scenario-a',json={})
    assert response.status_code==500 and 'error' in response.json()
    assert 'run_id' not in response.json() and 'publishable' not in response.json()

def test_handled_solver_error_is_terminal(boundary,instance,monkeypatch):
    client,state,actor=boundary
    def explode(*args):raise RuntimeError('sensitive implementation detail')
    monkeypatch.setattr(router,'optimise',explode)
    response=client.post(f'/api/ps1/instances/{instance["id"]}/optimise/scenario-a',json={})
    assert response.status_code==200,response.text
    body=response.json()
    assert body['solver_status']=='ERROR' and body['created'] and not body['publishable']
    assert body['submission_files'] is None and 'sensitive implementation detail' not in response.text
    assert state['saved'][0][1]=={'accesses':[],'occupancies':[],'contract_results':[]}

def test_invalid_reference_has_no_terminal_attempt(boundary,instance):
    client,state,actor=boundary
    response=client.post(f'/api/ps1/instances/{instance["id"]}/optimise/scenario-a',json={'locked_placements':[lock('MISSING').model_dump()]})
    assert response.status_code==422 and not state['saved'] and state['solves']==0

def test_export_consistency_failure_retains_only_diagnostic_candidate(boundary,instance,monkeypatch):
    client,state,actor=boundary
    def fail(*args):raise RuntimeError('Export integrity failure')
    monkeypatch.setattr(store,'schedule_records',fail)
    response=client.post(f'/api/ps1/instances/{instance["id"]}/optimise/scenario-a',json={})
    assert response.status_code==200
    body=response.json()
    assert body['solver_status']=='ERROR' and not body['publishable'] and body['submission_files'] is None
    assert body['failed_candidate']['diagnostic_only']
    assert body['failed_candidate']['result_snapshot']['physical_validation_complete']

def test_key_reuse_bypasses_solver(boundary,instance,accepted_result,monkeypatch):
    client,state,actor=boundary;rid=uuid4()
    saved={'id':rid,'created_at':datetime.now(timezone.utc),'terminal_outcome':'optimal','input_fingerprint':'a'*64,'result_snapshot':accepted_result.model_dump(mode='json')}
    monkeypatch.setattr(store,'existing_key',lambda *args,**kwargs:saved)
    response=client.post(f'/api/ps1/instances/{instance["id"]}/optimise/scenario-a',json={'idempotency_key':'reuse'})
    assert response.status_code==200 and response.json()['run_id']==str(rid)
    assert response.json()['reused'] and not response.json()['created']
    assert state['solves']==0 and not state['saved'] and state['commits']==1

def test_key_collision_has_no_solver_execution(boundary,instance,monkeypatch):
    client,state,actor=boundary
    def collision(*args,**kwargs):raise HTTPException(409,'Key collision')
    monkeypatch.setattr(store,'existing_key',collision)
    response=client.post(f'/api/ps1/instances/{instance["id"]}/optimise/scenario-a',json={'idempotency_key':'collision'})
    assert response.status_code==409 and state['solves']==0 and not state['saved']

def test_diagnostic_artifacts_are_blocked_and_scoped(boundary,monkeypatch):
    client,state,actor=boundary;rid=uuid4()
    monkeypatch.setattr(store,'get_run',lambda *args:{'publishable':False,'accepted_csvs':None})
    assert client.get(f'/api/ps1/optimisations/{rid}/artifacts').status_code==409
    def missing(*args,**kwargs):raise HTTPException(404,'PS1 optimisation not found')
    monkeypatch.setattr(store,'get_run',missing)
    for suffix in ('','/accesses','/occupancies','/artifacts'):
        assert client.get(f'/api/ps1/optimisations/{rid}{suffix}').status_code==404

def test_additive_contract_preserves_flags_and_complete_snapshot(accepted_result):
    accepted_result.primary_optimal=True;accepted_result.lexicographic_complete=False
    saved={'id':uuid4(),'created_at':datetime.now(timezone.utc),'terminal_outcome':'feasible','input_fingerprint':'a'*64,'result_snapshot':accepted_result.model_dump(mode='json')}
    response=store.response(saved,True).model_dump(mode='json')
    for key,value in accepted_result.model_dump(mode='json').items():assert response[key]==value
    assert response['primary_optimal'] and not response['lexicographic_complete']

def test_manual_smoke_fixture_is_importable_and_rich_feasible():
    from scripts.create_ps1_smoke_fixture import files
    from app.ps1 import load_files,parse_instance
    before=load_files();dataset=parse_instance(files())
    result=optimise(dataset,OptimiseInput(time_limit_seconds=5.0))
    assert result.publishable and result.physical_validation_complete
    assert len(result.physical_nights)==1 and result.physical_nights[0].activity_id=='SMOKE-A1'
    assert load_files()==before

def test_migration_seven_refuses_destructive_downgrade():
    import importlib
    revision=importlib.import_module('migrations.versions.0007_ps1_optimisation_runs')
    assert revision.down_revision=='0006'
    with pytest.raises(RuntimeError,match='Archive sealed'):revision.downgrade()

@pytest.mark.parametrize(('module','parent','message'),[
    ('0008_ps1_optimisation_jobs','0007','Archive optimisation jobs'),
    ('0009_ps1_optimisation_job_guards','0008','Archive optimisation job audit history'),
])
def test_job_migrations_parse_and_refuse_destructive_downgrade(monkeypatch,module,parent,message):
    import importlib
    from pglast import parse_sql
    revision=importlib.import_module('migrations.versions.'+module)
    calls=[]
    class Connection:
        def exec_driver_sql(self,sql,**options):
            assert options['execution_options']['no_parameters'] is True
            assert parse_sql(sql);calls.append(sql)
    monkeypatch.setattr(revision.op,'get_bind',lambda:Connection())
    assert revision.down_revision==parent
    revision.upgrade();assert calls
    with pytest.raises(RuntimeError,match=message):revision.downgrade()
