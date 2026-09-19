"""CP-SAT fixtures are generated independently; organiser sample is never a hint."""
import copy
import csv
import io
import random
from decimal import Decimal
from uuid import uuid4
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from app.main import app
from app.database import session
from app.dependencies import identity
from app.ps1 import parse_instance, load_files
from app.ps1_validation.network import chains, expand
from app.ps1_validation.service import validate
from app.ps1_optimisation.contracts import OptimiseInput, Placement
from app.ps1_optimisation.exporter import export_bundle
from app.ps1_optimisation.preprocessing import InputError, prepare
from app.ps1_optimisation.service import optimise
from scripts.audit_exported_closures import audit_files
from test_ps1_validation import fixture

def small(n=1, nature='Non-live (Others)', possession='C', work=1):
    ds,_=fixture(n=n,nature=nature,possession=possession,work=work)
    ds['parameters']['horizon_weeks']=4
    return ds

def run(ds, **kwargs):
    return optimise(ds,OptimiseInput(time_limit_seconds=5.0,**kwargs))

def lock(aid,week=1,night=1,seq=1,local=None):
    return Placement(activity_id=aid,access_seq=seq,week=week,physical_night=night,access_night=local)

def rows(result,name='SCHEDULE_ACCESS.csv'):
    return list(csv.DictReader(io.StringIO(result.submission_files[name])))

def assert_pass(result):
    assert result.publishable,(result.solver_status,result.diagnostics)
    assert result.physical_validation_complete
    assert result.validation_report.feasible
    assert result.validation_report.hard_violations==[]
    assert result.judge_validation=='not_run' and result.score_verification=='internal_only'

def test_complete_workload_no_eclo_sequences_and_rich_gate():
    ds=small(n=3,work=3)
    ds['tables']['project_details'][0]['number_of_workfronts']=3
    result=run(ds); assert_pass(result)
    assert len(rows(result))==9
    assert all(r['eclo']=='0' for r in rows(result))
    for aid in ('T0','T1','T2'):
        accesses=[r for r in result.physical_nights if r.activity_id==aid]
        assert [r.access_seq for r in accesses]==[1,2,3]
        assert len({r.week for r in accesses})==3
    assert result.validation_report.completeness.workload_gate_passed

def test_starts_and_dependencies():
    ds=small(n=2)
    ds['tables']['activity_details'][0]['planned_start_week']=2
    ds['tables']['activity_details'][1]['predecessor_activity_id']='T0'
    result=run(ds); assert_pass(result)
    a,b=result.physical_nights
    assert a.week>=2 and b.week>a.week

@pytest.mark.parametrize('kinds,legal',[
    (['PM'],True),(['PC'],True),(['C'],True),(['C']*4,True),(['PC']+['C']*3,True),
    (['PM','C'],False),(['PM','PC'],False),(['PM','PM'],False),(['PC','PC'],False),
    (['C']*5,False),(['PC']+['C']*4,False)])
def test_possession_mixes(kinds,legal):
    ds=small(n=len(kinds)); template=ds['tables']['project_details'][0]
    ds['tables']['project_details']=[]
    for i,kind in enumerate(kinds):
        contract=f'C{i}'
        ds['tables']['project_details'].append({**template,'contract_number':contract,'access_type':kind})
        ds['tables']['activity_details'][i]['contract_number']=contract
    result=run(ds,locked_placements=[lock(f'T{i}') for i in range(len(kinds))])
    assert result.publishable==legal
    if legal: assert_pass(result)
    else:
        assert result.solver_status=='INFEASIBLE'
        assert result.submission_files is None
        assert result.diagnostics[0]['code']=='infeasible_constraint_core'

@pytest.mark.parametrize('nature,second,rule',[
    ('Non-live (Consist)','SEC:ALP:S03_S04:EB','buffer'),
    ('Non-live (Consist)','SEC:ALP:S04_H01:EB','buffer'),
    ('Live','SEC:ALP:S01_S02:WB','live_opposite_bound'),
    ('Live','SEC:BET:H01_H02:EB','live_interchange')])
def test_distinct_possession_footprint_conflicts_apply_across_the_week(nature,second,rule):
    ds=small(n=2,nature=nature)
    a,b=ds['tables']['activity_details']
    if rule=='live_interchange': a['start_location_id']=a['end_location_id']='SEC:ALP:H01_H02:EB'
    b['start_location_id']=b['end_location_id']=second
    data=prepare(ds,OptimiseInput())
    assert rule in data['pairs'][0]['collisions']
    bad=run(ds,locked_placements=[lock('T0'),lock('T1')])
    assert bad.solver_status=='INFEASIBLE' and not bad.publishable
    assert run(ds,locked_placements=[lock('T0'),lock('T1',night=2)]).solver_status=='INFEASIBLE'
    good=run(ds,locked_placements=[lock('T0'),lock('T1',week=2,night=2)])
    assert_pass(good)

def test_same_location_distinct_groups_are_not_a_closure_escape():
    ds=small(n=2,possession='PM')
    for s in ds['tables']['location_supply']:s['supply_capacity']=2
    placements=[lock('T0'),lock('T1',night=2)]
    bad=run(ds,locked_placements=placements)
    assert bad.solver_status=='INFEASIBLE' and bad.submission_files is None
    good=run(ds,locked_placements=[lock('T0'),lock('T1',week=2,night=2)]); assert_pass(good)

def test_legal_sharing_uses_one_capacity_unit_but_full_workload():
    ds=small(n=4)
    ds['tables']['project_details'][0]['number_of_workfronts']=4
    for s in ds['tables']['location_supply']:s['supply_capacity']=1
    result=run(ds,locked_placements=[lock(f'T{i}') for i in range(4)])
    assert_pass(result)
    assert result.validation_report.completeness.activities_complete==4
    occupancy=rows(result,'SCHEDULE_OCCUPANCY.csv')
    assert all(len({row['co_share_group'] for row in occupancy if row['location_id']==loc})==1
        for loc in {row['location_id'] for row in occupancy})

def test_independent_export_audit_detects_split_group_regression():
    ds=small(n=2); ds['tables']['project_details'][0]['number_of_workfronts']=2
    result=run(ds,locked_placements=[lock('T0'),lock('T1')]); assert_pass(result)
    assert audit_files(ds,result.submission_files)['passed']
    files=dict(result.submission_files)
    files['SCHEDULE_OCCUPANCY.csv']='\n'.join(
        line.rsplit(',',1)[0]+',split' if line.startswith('T1,') else line
        for line in files['SCHEDULE_OCCUPANCY.csv'].splitlines())+'\n'
    audit=audit_files(ds,files)
    assert not audit['passed'] and audit['cross_group_closure_violation_count']>=2

def test_exporter_refuses_to_invent_split_possessions():
    ds=small(n=2)
    data=prepare(ds,OptimiseInput())
    with pytest.raises(ValueError,match='Invalid possession relationship'):
        export_bundle(ds,data,[lock('T0'),lock('T1',night=2)])

def test_physical_and_local_nights_independent():
    ds=small(n=2,possession='PM'); p=ds['tables']['project_details'][0]
    ds['tables']['project_details'].append({**p,'contract_number':'OTHER'})
    ds['tables']['activity_details'][1]['contract_number']='OTHER'
    ds['tables']['activity_details'][1]['start_location_id']=ds['tables']['activity_details'][1]['end_location_id']='SEC:ALP:S07_S08:EB'
    result=run(ds,locked_placements=[lock('T0',night=6,local=1),lock('T1',night=7,local=1)])
    assert_pass(result)
    assert {r.physical_night for r in result.physical_nights}=={6,7}
    assert {r.access_night for r in result.physical_nights}=={1}

def test_weekly_allocation_and_workfronts():
    ds=small(n=2); p=ds['tables']['project_details'][0]
    p['number_of_maximum_access_per_week']=1
    bad=run(ds,locked_placements=[lock('T0'),lock('T1',night=2)])
    assert bad.solver_status=='INFEASIBLE'
    p['number_of_workfronts']=1
    bad=run(ds,locked_placements=[lock('T0'),lock('T1')])
    assert bad.solver_status=='INFEASIBLE'
    good=run(ds); assert_pass(good)
    assert len({r.week for r in good.physical_nights})==2

def test_locks_and_baseline_are_distinct():
    ds=small(work=2)
    locked=[lock('T0',week=2,night=5,local=2),lock('T0',week=4,night=6,seq=2,local=3)]
    result=run(ds,locked_placements=locked,baseline_placements=[lock('T0'),lock('T0',week=2,seq=2)])
    assert_pass(result); assert result.physical_nights==locked
    assert result.completion_changes[0]['change_days']==14
    assert result.completion_changes[-1]['kind']=='contract'

def test_baseline_tiebreak_after_completion():
    ds=small()
    result=run(ds,baseline_placements=[lock('T0',night=6,local=2)])
    assert_pass(result); assert result.physical_nights==[lock('T0',night=6,local=2)]
    late=run(ds,baseline_placements=[lock('T0',week=4)])
    assert_pass(late); assert late.physical_nights[0].week==1

def test_canonical_occupancy_and_results_independent_of_cached_spans():
    ds=small(); ds['tables']['activity_details'][0]['span_location_ids']=[]
    result=run(ds); assert_pass(result)
    expected=expand(ds['tables']['activity_details'][0],ds['tables']['project_details'][0],chains(ds))['occupied']
    assert {r['location_id'] for r in rows(result,'SCHEDULE_OCCUPANCY.csv')}==expected
    assert rows(result,'RESULTS.csv')[0]['simulated_completion_date']=='2027-01-10'
    mapping={(r.activity_id,r.week):r.physical_night for r in result.physical_nights}
    assert validate(ds,result.submission_files,'A',physical_nights=mapping)['feasible']

@pytest.mark.parametrize('tier,priority,expected',[(1,1,'910.00'),(2,2,'84.00'),(3,3,'7.00')])
def test_exact_scaled_priority_objective(tier,priority,expected):
    ds=small(); ds['tables']['project_details'][0]['contract_priority']=tier
    ds['tables']['activity_details'][0]['activity_priority']=priority
    result=run(ds,locked_placements=[lock('T0',week=2)])
    assert_pass(result)
    assert result.validation_report.objective_score==expected
    assert Decimal(result.stages[0]['value'])/10==Decimal(expected)
    assert all(stage['status']=='OPTIMAL' for stage in result.stages)

def test_stable_seed_and_dataset_order():
    ds=small(n=3,work=2); ds['tables']['project_details'][0]['number_of_workfronts']=3
    first=run(ds,random_seed=42)
    assert_pass(first)
    shuffled=copy.deepcopy(ds)
    for table in shuffled['tables'].values():random.Random(7).shuffle(table)
    second=run(shuffled,random_seed=42); assert_pass(second)
    assert first.submission_files==second.submission_files
    assert first.physical_nights==second.physical_nights
    assert first.validation_report==second.validation_report

def test_primary_objective_dominates_baseline_and_stable_ties():
    ds=small(n=2,possession='PM'); ds['parameters']['horizon_weeks']=2
    p=ds['tables']['project_details'][0];p['contract_priority']=1
    ds['tables']['project_details'].append({**p,'contract_number':'LOW','contract_priority':3})
    ds['tables']['activity_details'][1]['contract_number']='LOW'
    for supply in ds['tables']['location_supply']:supply['supply_capacity']=1
    result=run(ds,baseline_placements=[lock('T0',week=2),lock('T1',week=1)])
    assert_pass(result)
    assert [(r.activity_id,r.week) for r in result.physical_nights]==[('T0',1),('T1',2)]
    assert result.validation_report.objective_score=='7.00'

@pytest.mark.parametrize('sector',['SEC:ALP:S01_S02:EB','SEC:ALP:S07_S08:EB'])
@pytest.mark.parametrize('nature',['Live','Non-live (Consist)'])
def test_boundary_footprints_used_without_wrapping(sector,nature):
    ds=small(nature=nature)
    a=ds['tables']['activity_details'][0];a['start_location_id']=a['end_location_id']=sector
    data=prepare(ds,OptimiseInput())
    footprint=data['footprints']['T0']
    assert not footprint['interchange']
    assert len(footprint['buffer'])==(4 if nature=='Live' else 2)
    assert_pass(run(ds))

def test_infeasible_dependency_and_inconsistent_lock_sequences():
    ds=small(n=2,work=3)
    ds['tables']['activity_details'][1]['predecessor_activity_id']='T0'
    result=run(ds)
    assert result.solver_status=='INFEASIBLE' and not result.publishable
    result=run(small(work=2),locked_placements=[lock('T0',week=3),lock('T0',week=2,seq=2)])
    assert result.solver_status=='INFEASIBLE' and result.submission_files is None

def test_cli_offline_success_and_no_overwrite(tmp_path,monkeypatch):
    import json
    import sys
    import app.ps1_optimisation.__main__ as cli
    monkeypatch.setattr(cli,'parse_instance',lambda files:small())
    output=tmp_path/'candidate'
    monkeypatch.setattr(sys,'argv',['optimise','--output',str(output)])
    assert cli.main()==0
    assert {p.name for p in output.iterdir()}=={'report.json','SCHEDULE_ACCESS.csv','SCHEDULE_OCCUPANCY.csv','RESULTS.csv'}
    assert json.loads((output/'report.json').read_text())['physical_validation_complete']
    with pytest.raises(SystemExit):cli.main()

def test_cli_no_csvs_on_failed_solve(tmp_path,monkeypatch):
    import sys
    import app.ps1_optimisation.__main__ as cli
    monkeypatch.setattr(cli,'parse_instance',lambda files:small(work=5))
    output=tmp_path/'failed'
    monkeypatch.setattr(sys,'argv',['optimise','--output',str(output)])
    assert cli.main()==2
    assert {p.name for p in output.iterdir()}=={'report.json'}

@pytest.mark.parametrize('field,value',[('time_limit_seconds',0),('time_limit_seconds',121),('random_seed',-1),('random_seed',True),('physical_nights_per_week',0),('physical_nights_per_week',8),('deterministic_time_limit',0),('scenario','B')])
def test_safe_request_bounds(field,value):
    with pytest.raises(ValidationError):OptimiseInput(**{field:value})

@pytest.mark.parametrize('placements',[[lock('UNKNOWN')],[lock('T0',seq=2)],[lock('T0'),lock('T0')],[lock('T0',week=5)],[lock('T0',local=4)]])
def test_bad_placement_references(placements):
    with pytest.raises(InputError):run(small(),locked_placements=placements)

def test_impossible_workload_zero_supply_and_model_limits():
    ds=small(work=5); result=run(ds)
    assert result.solver_status=='INFEASIBLE' and result.submission_files is None
    ds=small()
    for s in ds['tables']['location_supply']:s['supply_capacity']=0
    result=run(ds); assert result.solver_status=='INFEASIBLE'
    ds=small(n=30);ds['parameters']['horizon_weeks']=520
    result=run(ds); assert result.solver_status=='MODEL_LIMIT'
    assert not result.publishable and result.submission_files is None

def test_gate_rejects_candidate_without_publishable_files(monkeypatch):
    import app.ps1_optimisation.service as service
    real=service.validate
    def reject(*args,**kwargs):
        report=real(*args,**kwargs); report['feasible']=False
        report['hard_violations']=[{'rule_code':'buffer','message':'forced gate test','activity_ids':['T0'],'contract_ids':[],'location_ids':[],'week':1,'possession_group':None,'evidence':{}}]
        report['objective_score']=None
        return report
    monkeypatch.setattr(service,'validate',reject)
    result=run(small())
    assert result.solver_status=='VALIDATION_FAILED' and not result.publishable
    assert result.submission_files is None and result.physical_nights==[]
    assert result.failed_candidate['diagnostic_only']

def test_incomplete_physical_gate_also_rejects(monkeypatch):
    import app.ps1_optimisation.service as service
    real=service.validate
    def incomplete(*args,**kwargs):
        report=real(*args,**kwargs);report['physical_validation_complete']=False;return report
    monkeypatch.setattr(service,'validate',incomplete)
    result=run(small()); assert result.solver_status=='VALIDATION_FAILED'

def test_public_dataset_bounded_solve_never_fabricates():
    result=optimise(parse_instance(load_files()),OptimiseInput(time_limit_seconds=3.0,deterministic_time_limit=0.1))
    if result.publishable:
        assert_pass(result); assert len(result.physical_nights)==192
    else:
        assert result.solver_status in {'UNKNOWN','INFEASIBLE'}
        assert result.submission_files is None and result.physical_nights==[]
        assert result.diagnostics

def test_stateless_scenario_a_preview_without_database_or_auth(monkeypatch):
    monkeypatch.delenv('DATABASE_URL',raising=False)
    monkeypatch.delenv('RAILPLAN_DEMO_AUTH',raising=False)
    payload={'instance_files':load_files(),'time_limit_seconds':3.0,'deterministic_time_limit':0.1}
    with TestClient(app) as preview_client:
        response=preview_client.post('/api/ps1/optimise/scenario-a/preview',json=payload)
        assert response.status_code==200,response.text
        result=response.json()
        assert result['judge_validation']=='not_run' and result['score_verification']=='internal_only'
        if result['publishable']:
            assert result['physical_validation_complete']
            assert result['validation_report']['validation_context']=='rich_schedule'
            assert result['validation_report']['hard_violations']==[]
            assert len(result['physical_nights'])==192
            assert set(result['submission_files'])=={'SCHEDULE_ACCESS.csv','SCHEDULE_OCCUPANCY.csv','RESULTS.csv'}
        else:
            assert result['solver_status'] in {'UNKNOWN','INFEASIBLE','MODEL_INVALID','MODEL_LIMIT'}
            assert result['submission_files'] is None and result['physical_nights']==[]
        bad=preview_client.post('/api/ps1/optimise/scenario-a/preview',json={**payload,'instance_files':{'01_LINES.csv':'bad'}})
        assert bad.status_code==422

@pytest.fixture
def client(monkeypatch):
    from app.routers import ps1_optimisation as router
    from app.ps1_optimisation.saved_contracts import SavedOptimiseResult
    from contextlib import nullcontext
    from datetime import datetime,timezone
    class Boundary:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def begin(self):return nullcontext()
    app.dependency_overrides[session]=lambda:object()
    actor={'id':uuid4(),'operator_id':uuid4(),'roles':{'planner'}}
    app.dependency_overrides[identity]=lambda:actor
    app.dependency_overrides[router.optimisation_session_factory]=lambda:Boundary
    monkeypatch.setattr(router,'identity',lambda request,db,user:app.dependency_overrides[identity]())
    monkeypatch.setattr(router,'get_instance',lambda db,actor,instance_id:{'id':instance_id,'dataset':small()})
    monkeypatch.setattr(router.store,'existing_key',lambda *args,**kwargs:None)
    def save(db,actor,instance,payload,configuration,digest,result,records,started,completed):
        return SavedOptimiseResult(**result.model_dump(),run_id=uuid4(),created=True,reused=False,
            created_at=datetime.now(timezone.utc),terminal_outcome=router.store.OUTCOMES[result.solver_status],input_fingerprint=digest)
    monkeypatch.setattr(router.store,'persist',save)
    with TestClient(app) as test_client:yield test_client
    app.dependency_overrides.clear()

def test_api_success_and_contract(client):
    response=client.post(f'/api/ps1/instances/{uuid4()}/optimise/scenario-a',json={})
    assert response.status_code==200,response.text
    assert response.json()['publishable'] and response.json()['physical_validation_complete']
    assert response.json()['judge_validation']=='not_run'

def test_api_role_scope_and_error_envelope(client,monkeypatch):
    from app.routers import ps1_optimisation as router
    path=f'/api/ps1/instances/{uuid4()}/optimise/scenario-a'
    app.dependency_overrides[identity]=lambda:{'roles':{'viewer'}}
    response=client.post(path,json={}); assert response.status_code==403
    assert response.json()['error']['code']=='FORBIDDEN'
    app.dependency_overrides[identity]=lambda:{'roles':{'planner'}}
    def missing(*args):raise HTTPException(404,'PS1 instance not found')
    monkeypatch.setattr(router,'get_instance',missing)
    assert client.post(path,json={}).status_code==404

def test_api_invalid_options_and_references(client):
    path=f'/api/ps1/instances/{uuid4()}/optimise/scenario-a'
    for payload in ({'physical_nights_per_week':8},{'locked_placements':[lock('UNKNOWN').model_dump()]}):
        response=client.post(path,json=payload)
        assert response.status_code==422 and response.json()['error']['code']=='INVALID_INPUT'
