"""Scenario B generation tests; validator rule families are covered separately."""
import csv
import io
import sys
from copy import deepcopy
from decimal import Decimal

from fastapi.testclient import TestClient

from app.main import app
from app.ps1_optimisation.contracts import Placement, ScenarioBOptimiseInput
from app.ps1_optimisation.service import optimise_scenario_b
from app.ps1_validation.service import validate
from test_ps1_optimisation import small


def deadline(dataset, value='2027-02-28'):
    for project in dataset['tables']['project_details']:
        project['planned_completion_date']=value
    return dataset


def run(dataset, **kwargs):
    return optimise_scenario_b(dataset,ScenarioBOptimiseInput(time_limit_seconds=5,**kwargs))


def access_rows(result):
    return list(csv.DictReader(io.StringIO(result.submission_files['SCHEDULE_ACCESS.csv'])))


def test_scaled_workload_and_eclo_are_exact_and_exported():
    result=run(deadline(small(work=3),'2027-01-17'))
    assert result.publishable and result.scenario=='B'
    assert [(r['access_seq'],r['week'],r['eclo']) for r in access_rows(result)]==[('1','1','1'),('2','2','1')]
    item=result.workload_delivery[0]
    assert item['required']=='3.0' and item['delivered']=='3.0' and item['over_delivery']=='0.0'
    assert result.objective_components['eclo_nights_total']==2
    assert result.objective_components['eclo_penalty']=='10.00'


def test_normal_access_and_avoidable_overdelivery_win_when_deadline_allows():
    result=run(deadline(small(work=3)))
    assert result.publishable
    assert len(access_rows(result))==3
    assert {r['eclo'] for r in access_rows(result)}=={'0'}
    assert result.objective_components['diagnostic_objective']=='0.00'
    assert result.workload_delivery[0]['over_delivery']=='0.0'


def test_forced_late_completion_is_infeasible_and_has_no_artifacts():
    result=run(small(work=3))
    assert result.solver_status=='INFEASIBLE'
    assert not result.publishable and result.submission_files is None
    assert any(d['code']=='infeasible_constraint_core' for d in result.diagnostics)


def test_results_come_from_validator_completion_policy():
    result=run(deadline(small(work=2),'2027-01-17'))
    assert result.publishable and result.contract_completion_gate
    row=list(csv.DictReader(io.StringIO(result.submission_files['RESULTS.csv'])))[0]
    assert row=={'scenario':'B','contract_number':'C006','simulated_completion_date':'2027-01-17','overrun_days':'0'}
    mapping={(p.activity_id,p.week):p.physical_night for p in result.physical_nights}
    report=validate(deadline(small(work=2),'2027-01-17'),result.submission_files,'B',physical_nights=mapping)
    assert report['feasible'] and report['objective_score']==result.validation_report.objective_score


def test_capacity_excess_is_allowed_and_scored_per_location_week():
    dataset=deadline(small())
    footprint={'PLAT:ALP:S01:EB','SEC:ALP:S01_S02:EB','PLAT:ALP:S02:EB'}
    for row in dataset['tables']['location_supply']:
        row['supply_capacity']=0 if row['location_id'] in footprint else 1
    result=run(dataset)
    assert result.publishable
    assert result.objective_components['excess_access_nights_total']==3
    assert result.objective_components['excess_penalty']=='21.00'
    assert result.validation_report.objective_score=='21.00'
    assert all({'available_supply','used_possession_groups','activity_ids','contract_ids','co_share_groups','physical_night_assignments'}<=set(row) for row in result.capacity_hotspots)


def test_legal_co_share_consumes_one_unit_and_cannot_be_split_into_groups():
    dataset=deadline(small(n=2))
    dataset['tables']['project_details'][0]['number_of_workfronts']=2
    for row in dataset['tables']['location_supply']:row['supply_capacity']=1
    shared=run(dataset,locked_placements=[Placement(activity_id=f'T{i}',access_seq=1,week=1,physical_night=1,access_night=1,eclo=0) for i in range(2)])
    assert shared.publishable and shared.objective_components['excess_access_nights_total']==0
    separate=run(dataset,locked_placements=[Placement(activity_id='T0',access_seq=1,week=1,physical_night=1,access_night=1,eclo=0),Placement(activity_id='T1',access_seq=1,week=1,physical_night=2,access_night=2,eclo=0)])
    assert separate.solver_status=='INFEASIBLE' and separate.submission_files is None


def test_distinct_possession_buffer_conflict_applies_across_week():
    dataset=deadline(small(n=2,nature='Non-live (Consist)'))
    dataset['tables']['activity_details'][1]['start_location_id']=dataset['tables']['activity_details'][1]['end_location_id']='SEC:ALP:S03_S04:EB'
    a=Placement(activity_id='T0',access_seq=1,week=1,physical_night=1,access_night=1,eclo=0)
    b=Placement(activity_id='T1',access_seq=1,week=1,physical_night=1,access_night=1,eclo=0)
    assert run(dataset,locked_placements=[a,b]).solver_status=='INFEASIBLE'
    assert run(dataset,locked_placements=[a,b.model_copy(update={'physical_night':2,'access_night':2})]).solver_status=='INFEASIBLE'
    assert run(dataset,locked_placements=[a,b.model_copy(update={'week':2,'physical_night':2,'access_night':2})]).publishable


def test_legal_possession_label_does_not_bypass_physical_buffer():
    dataset=deadline(small(n=2,nature='Non-live (Consist)'))
    for activity in dataset['tables']['activity_details']:
        activity['start_location_id']=activity['end_location_id']='SEC:ALP:S01_S02:EB'
    locks=[Placement(activity_id=f'T{i}',access_seq=1,week=1,physical_night=1,access_night=1,eclo=0) for i in range(2)]
    result=run(dataset,locked_placements=locks)
    assert result.solver_status=='INFEASIBLE' and result.submission_files is None


def test_locks_baseline_and_fixed_seed_are_deterministic():
    dataset=deadline(small(work=2),'2027-01-17')
    lock=Placement(activity_id='T0',access_seq=1,week=1,physical_night=5,access_night=2,eclo=0)
    options={'locked_placements':[lock],'baseline_placements':[lock.model_copy(update={'physical_night':4})],'random_seed':41}
    first=run(deepcopy(dataset),**options);second=run(deepcopy(dataset),**options)
    assert first.publishable and first.physical_nights==second.physical_nights
    assert first.submission_files==second.submission_files
    assert first.physical_nights[0].physical_night==5 and first.baseline_movement==1


def test_stages_preserve_official_objective_and_headers():
    result=run(deadline(small(work=3),'2027-01-17'))
    assert result.publishable
    values={stage['name']:stage['value'] for stage in result.stages}
    assert values['official_scenario_b_objective']==10
    assert Decimal(result.validation_report.objective_score)==Decimal(values['official_scenario_b_objective'])
    assert all(stage['status']=='OPTIMAL' and stage['optimality_proven'] for stage in result.stages)
    assert result.submission_files['SCHEDULE_ACCESS.csv'].splitlines()[0]=='activity_id,access_seq,week,eclo,access_night'
    assert result.submission_files['SCHEDULE_OCCUPANCY.csv'].splitlines()[0]=='activity_id,week,location_id,co_share_group'
    assert result.submission_files['RESULTS.csv'].splitlines()[0]=='scenario,contract_number,simulated_completion_date,overrun_days'
    assert 'physical_night' not in result.submission_files['SCHEDULE_ACCESS.csv'].splitlines()[0]


def test_stateless_preview_requires_no_database(monkeypatch):
    from scripts.create_ps1_smoke_fixture import files
    monkeypatch.delenv('DATABASE_URL',raising=False)
    with TestClient(app) as client:
        response=client.post('/api/ps1/optimise/scenario-b/preview',json={'instance_files':files(),'time_limit_seconds':2})
    assert response.status_code==200,response.text
    body=response.json()
    assert body['scenario']=='B' and body['judge_validation']=='not_run' and body['score_verification']=='internal_only'
    assert body['publishable'] and body['submission_files']


def test_official_dataset_bounded_never_fabricates_artifacts():
    from app.ps1 import load_files,parse_instance
    result=optimise_scenario_b(parse_instance(load_files()),ScenarioBOptimiseInput(time_limit_seconds=.5,deterministic_time_limit=.03))
    if result.publishable:
        assert result.validation_report.feasible and result.physical_validation_complete
    else:
        assert result.submission_files is None and result.physical_nights==[]
        assert result.solver_status in {'UNKNOWN','INFEASIBLE'}
