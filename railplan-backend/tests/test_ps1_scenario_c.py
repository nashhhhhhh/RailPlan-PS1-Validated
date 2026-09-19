"""Scenario C balanced-objective and line-window generation tests."""
import csv
import io
import sys
from copy import deepcopy
from decimal import Decimal

from fastapi.testclient import TestClient

from app.main import app
from app.ps1_optimisation.contracts import OptimiseInput,Placement,ScenarioCOptimiseInput
from app.ps1_optimisation.preprocessing import prepare
from app.ps1_optimisation.service import optimise_scenario_c
from test_ps1_optimisation import small


def run(dataset,**kwargs):
    return optimise_scenario_c(dataset,ScenarioCOptimiseInput(time_limit_seconds=5,**kwargs))


def primary(result):
    return next(stage for stage in result.stages if stage['name']=='official_scenario_c_objective_scaled_10')


def accesses(result):
    return list(csv.DictReader(io.StringIO(result.submission_files['SCHEDULE_ACCESS.csv'])))


def lock(aid,seq,week,night=1,eclo=1,local=1):
    return Placement(activity_id=aid,access_seq=seq,week=week,physical_night=night,access_night=local,eclo=eclo)


def test_scaled_workload_eclo_window_and_exact_official_objective():
    dataset=small(work=3);dataset['tables']['project_details'][0]['contract_priority']=1
    result=run(dataset)
    assert result.publishable and result.scenario=='C'
    assert [(row['week'],row['eclo']) for row in accesses(result)]==[('1','1'),('2','1')]
    assert result.eclo_windows['ALP']=={'active':True,'start_week':1,'end_week':2,'activity_ids':['T0']}
    item=result.workload_delivery[0]
    assert (item['required'],item['delivered'],item['standard_access_contribution'],item['eclo_contribution'])==('3.0','3.0','0.0','3.0')
    components=result.objective_components
    expected=Decimal(components['priority_weighted_overrun'])+Decimal(7*components['excess_access_nights_total']+5*components['eclo_nights_total'])
    assert Decimal(result.validation_report.objective_score)==expected
    assert Decimal(primary(result)['value'])/10==expected


def test_no_eclo_keeps_both_line_windows_inactive():
    result=run(small())
    assert result.publishable
    assert all(window['active'] is False and window['start_week'] is None and window['end_week'] is None for window in result.eclo_windows.values())


def test_scenario_a_full_shared_overlap_is_not_assumed_valid_for_c_buffers():
    """Regression for the rejected organiser A-to-C conversion audit."""
    dataset=small(n=2,nature='Non-live (Consist)')
    scenario_a=prepare(dataset,OptimiseInput(),'A')
    scenario_c=prepare(dataset,ScenarioCOptimiseInput(),'C')
    assert scenario_a['pairs']==[]  # Established Scenario A full-sharing exemption.
    assert len(scenario_c['pairs'])==1
    assert 'buffer' in scenario_c['pairs'][0]['collisions']


def test_two_consecutive_weeks_valid_but_disconnected_or_three_week_span_infeasible():
    dataset=small(work=3)
    assert run(deepcopy(dataset),locked_placements=[lock('T0',1,1),lock('T0',2,2)]).publishable
    boundary=run(deepcopy(dataset),locked_placements=[lock('T0',1,3),lock('T0',2,4)])
    assert boundary.publishable and boundary.eclo_windows['ALP']['start_week']==3 and boundary.eclo_windows['ALP']['end_week']==4
    bad=run(deepcopy(dataset),locked_placements=[lock('T0',1,1),lock('T0',2,3)])
    assert bad.solver_status=='INFEASIBLE' and bad.submission_files is None
    dataset['tables']['activity_details'][0]['total_accesses']=4
    three=run(dataset,locked_placements=[lock('T0',1,1),lock('T0',2,2),lock('T0',3,3)])
    assert three.solver_status=='INFEASIBLE' and three.submission_files is None


def test_alpha_and_beta_windows_are_independent():
    dataset=small(n=2,work=3)
    dataset['tables']['project_details'][0]['number_of_workfronts']=2
    beta=dataset['tables']['activity_details'][1]
    beta['start_location_id']=beta['end_location_id']='SEC:BET:S11_S12:EB'
    locks=[lock('T0',1,1),lock('T0',2,2),lock('T1',1,3),lock('T1',2,4)]
    result=run(dataset,locked_placements=locks)
    assert result.publishable
    assert (result.eclo_windows['ALP']['start_week'],result.eclo_windows['ALP']['end_week'])==(1,2)
    assert (result.eclo_windows['BET']['start_week'],result.eclo_windows['BET']['end_week'])==(3,4)


def test_cross_line_live_eclo_activates_both_windows():
    dataset=small(work=1,nature='Live')
    activity=dataset['tables']['activity_details'][0]
    activity['start_location_id']=activity['end_location_id']='SEC:ALP:H01_H02:EB'
    result=run(dataset,locked_placements=[lock('T0',1,2)])
    assert result.publishable and result.cross_line_eclo_activities==['T0']
    assert all(window['active'] and window['start_week']==window['end_week']==2 for window in result.eclo_windows.values())


def test_one_capacity_excess_per_location_is_allowed_and_two_is_infeasible():
    dataset=small(n=2)
    dataset['tables']['project_details'][0]['number_of_workfronts']=2
    footprint={'PLAT:ALP:S01:EB','SEC:ALP:S01_S02:EB','PLAT:ALP:S02:EB'}
    for row in dataset['tables']['location_supply']:
        if row['location_id'] in footprint:row['supply_capacity']=0
    shared=run(deepcopy(dataset),locked_placements=[lock('T0',1,1,eclo=0),lock('T1',1,1,eclo=0)])
    assert shared.publishable and shared.objective_components['excess_access_nights_total']==3
    assert all(row['excess']==1 and row['hard_max_reached'] and row['physical_night_assignments'] for row in shared.capacity_hotspots)
    separate=run(dataset,locked_placements=[lock('T0',1,1,eclo=0),lock('T1',1,1,night=2,eclo=0,local=2)])
    assert separate.solver_status=='INFEASIBLE' and separate.submission_files is None


def test_activity_weighting_raw_contract_overrun_and_decimal_scale_match_validator():
    dataset=small(n=2)
    dataset['tables']['project_details'][0]['number_of_workfronts']=2
    dataset['tables']['activity_details'][0]['activity_priority']=1
    dataset['tables']['activity_details'][1]['activity_priority']=3
    result=run(dataset,locked_placements=[lock('T0',1,2,eclo=0),lock('T1',1,3,eclo=0)])
    assert result.publishable
    components=result.objective_components
    assert components['priority_weighted_overrun']=='23.10'
    assert components['overrun_days_total']==14
    assert components['diagnostic_objective']=='23.10'
    assert primary(result)['value']==231


def test_headers_scenario_value_and_no_internal_columns():
    result=run(small())
    assert result.publishable
    assert result.submission_files['SCHEDULE_ACCESS.csv'].splitlines()[0]=='activity_id,access_seq,week,eclo,access_night'
    assert result.submission_files['SCHEDULE_OCCUPANCY.csv'].splitlines()[0]=='activity_id,week,location_id,co_share_group'
    results=result.submission_files['RESULTS.csv'].splitlines()
    assert results[0]=='scenario,contract_number,simulated_completion_date,overrun_days' and results[1].startswith('C,')
    assert 'physical_night' not in result.submission_files['SCHEDULE_ACCESS.csv'] and 'window' not in result.submission_files['SCHEDULE_ACCESS.csv']


def test_fixed_seed_locks_baseline_and_completed_output_are_stable():
    dataset=small(work=2)
    options={'random_seed':37,'locked_placements':[lock('T0',1,1,night=5,eclo=0,local=2)],
        'baseline_placements':[lock('T0',1,1,night=4,eclo=0,local=2)]}
    first=run(deepcopy(dataset),**options);second=run(deepcopy(dataset),**options)
    assert first.publishable and first.physical_nights==second.physical_nights
    assert first.submission_files==second.submission_files and first.baseline_movement==1


def test_stateless_preview_requires_no_database(monkeypatch):
    from scripts.create_ps1_smoke_fixture import files
    monkeypatch.delenv('DATABASE_URL',raising=False)
    with TestClient(app) as client:
        response=client.post('/api/ps1/optimise/scenario-c/preview',json={'instance_files':files(),'time_limit_seconds':2})
    assert response.status_code==200,response.text
    body=response.json()
    assert body['scenario']=='C' and body['publishable'] and body['judge_validation']=='not_run' and body['score_verification']=='internal_only'


def test_official_dataset_bounded_never_fabricates_artifacts():
    from app.ps1 import load_files,parse_instance
    result=optimise_scenario_c(parse_instance(load_files()),ScenarioCOptimiseInput(time_limit_seconds=.5,deterministic_time_limit=.03))
    if result.publishable:
        assert result.validation_report.feasible and result.physical_validation_complete
    else:
        assert result.submission_files is None and result.physical_nights==[]
        assert result.solver_status in {'UNKNOWN','INFEASIBLE'}
