"""Public baseline plus focused mutations; no official validator is bundled."""
import copy
import csv
import io
import json
import random
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.ps1 import parse_instance, load_files
from app.ps1_validation.contracts import HEADERS, POLICY, VERSION, RULES
from app.ps1_validation.network import chains, expand
from app.ps1_validation.rules import legal_mix
from app.ps1_validation.service import validate
from app.ps1_validation.submission import fingerprint

def sample_files():
    return {p.name:p.read_text() for p in (Path(__file__).resolve().parents[1]/'data/PS1/03_submission_sample').glob('*.csv')}

def encode(rows):
    files={}
    for name,header in HEADERS.items():
        stream=io.StringIO(); writer=csv.DictWriter(stream,fieldnames=header.split(','),lineterminator='\n')
        writer.writeheader(); writer.writerows(rows[name]); files[name]=stream.getvalue()
    return files

def decode(files):
    return {name:list(csv.DictReader(io.StringIO(value))) for name,value in files.items()}

def fixture(n=1,nature='Non-live (Others)',possession='C',week=1,work=1):
    ds=parse_instance(load_files())
    project=copy.deepcopy(ds['tables']['project_details'][5])
    project.update(nature_of_activity=nature,access_type=possession,planned_completion_date='2027-01-10',contract_priority=3)
    activity=copy.deepcopy(ds['tables']['activity_details'][0])
    activity.update(contract_number=project['contract_number'],activity_type=project['activity_type'],
        start_location_id='SEC:ALP:S01_S02:EB',end_location_id='SEC:ALP:S01_S02:EB',
        total_accesses=work,planned_start_week=1,planned_start_date='2027-01-04',predecessor_activity_id='',activity_priority=3)
    ds['tables']['project_details']=[project]
    ds['tables']['activity_details']=[{**activity,'activity_id':f'T{i}'} for i in range(n)]
    rows={name:[] for name in HEADERS}
    for i in range(n):
        rows['SCHEDULE_ACCESS.csv'].append(dict(activity_id=f'T{i}',access_seq=1,week=week,eclo=0,access_night=i+1))
    refresh(ds,rows)
    return ds,rows

def refresh(ds,rows,scenario='A'):
    """Rebuild well-formed occupancy/results after a deliberate test mutation."""
    net=chains(ds); activities={a['activity_id']:a for a in ds['tables']['activity_details']}
    projects={(p['contract_number'],p['activity_type']):p for p in ds['tables']['project_details']}
    rows['SCHEDULE_OCCUPANCY.csv']=[]
    end={}
    for r in rows['SCHEDULE_ACCESS.csv']:
        a=activities[r['activity_id']]; p=projects[a['contract_number'],a['activity_type']]
        for loc in sorted(expand(a,p,net)['occupied']):
            rows['SCHEDULE_OCCUPANCY.csv'].append(dict(activity_id=a['activity_id'],week=r['week'],location_id=loc,co_share_group='slot'))
        end[a['contract_number']]=max(end.get(a['contract_number'],0),r['week'])
    rows['RESULTS.csv']=[]
    for contract,week in sorted(end.items()):
        p=next(p for p in projects.values() if p['contract_number']==contract)
        complete=date.fromisoformat(ds['parameters']['horizon_start'])+timedelta(weeks=week,days=-1)
        rows['RESULTS.csv'].append(dict(scenario=scenario,contract_number=contract,simulated_completion_date=complete.isoformat(),
            overrun_days=max(0,(complete-date.fromisoformat(p['planned_completion_date'])).days)))

def codes(ds,rows,scenario='A',physical_nights=None):
    return {v['rule_code'] for v in validate(ds,encode(rows),scenario,physical_nights)['hard_violations']}

def test_public_sample_baseline():
    r=validate(parse_instance(load_files()),sample_files(),'A')
    assert r['hard_violations']==[]
    assert len(r['warnings'])==70
    assert all(w['code']=='physical_night_alignment_unverifiable' for w in r['warnings'])
    assert r['completeness']['activities_complete']==54
    assert r['objective_components']['nights_scheduled']==192
    assert r['objective_components']['priority_weighted_overrun']=='48.30'
    assert r['objective_components']['overrun_days_total']==28
    assert r['objective_components']['excess_access_nights_total']==0
    assert r['objective_score']=='48.30' and r['feasible']
    assert r['validation_status']=='feasible'
    assert not r['physical_validation_complete']
    assert r['judge_validation']=='not_run' and r['validator_version']==VERSION

def test_public_canonical_spans_ignore_cached_data():
    ds=parse_instance(load_files()); original=validate(ds,sample_files(),'A')
    for a in ds['tables']['activity_details']: a['span_location_ids']=[]
    assert validate(ds,sample_files(),'A')==original

@pytest.mark.parametrize('seed',range(5))
def test_deterministic_order(seed):
    ds=parse_instance(load_files()); files=sample_files(); original=validate(ds,files,'A')
    rng=random.Random(seed)
    for table in ds['tables'].values(): rng.shuffle(table)
    assert validate(ds,files,'A')==original
    rows=decode(files)
    for table in rows.values(): rng.shuffle(table)
    reordered=validate(ds,encode(rows),'A')
    assert reordered.pop('submission_fingerprint')!=original.pop('submission_fingerprint')
    assert reordered==original

@pytest.mark.parametrize('types,valid',[
 (['PM'],True),(['PC'],True),(['C'],True),(['C']*4,True),(['PC']+['C']*3,True),
 (['PM','C'],False),(['PM','PC'],False),(['PM','PM'],False),(['PC','PC'],False),
 (['C']*5,False),(['PC']+['C']*4,False),([],False)])
def test_possession_mixes(types,valid):
    assert legal_mix(types)==valid

@pytest.mark.parametrize('nature,radius',[('Live',2),('Non-live (Consist)',1),('Non-live (Others)',0)])
@pytest.mark.parametrize('end',['left','right'])
def test_buffers_clip_both_line_boundaries(nature,radius,end):
    ds,rows=fixture(nature=nature); a=ds['tables']['activity_details'][0]; p=ds['tables']['project_details'][0]
    if end=='right': a['start_location_id']=a['end_location_id']='SEC:ALP:S07_S08:EB'
    result=expand(a,p,chains(ds)); chain=chains(ds)['ALP','EB']
    expected=set(chain[:3+2*radius] if end=='left' else chain[-(3+2*radius):])
    assert result['occupied']|result['buffer']==expected
    assert len(result['opposite'])==(len(expected) if nature=='Live' else 0)
    assert not result['interchange']

@pytest.mark.parametrize('nature',['Live','Non-live (Consist)','Non-live (Others)'])
def test_live_only_interchange(nature):
    ds,rows=fixture(nature=nature); a=ds['tables']['activity_details'][0]
    a['start_location_id']=a['end_location_id']='SEC:ALP:H01_H02:EB'
    result=expand(a,ds['tables']['project_details'][0],chains(ds))
    assert len(result['interchange'])==(6 if nature=='Live' else 0)
    assert result['lines']==({'ALP','BET'} if nature=='Live' else {'ALP'})

def test_all_hard_families_are_exercised():
    assert set(RULES)=={'schema','unknown_reference','duplicate','workload','access_sequence','weekly_activity_access',
        'planned_start','dependency','occupancy','possession_mix','closure','buffer','live_opposite_bound','live_interchange',
        'capacity','weekly_allocation','workfront','eclo','eclo_window','planned_date','results_consistency'}

@pytest.mark.parametrize('family', ['schema','unknown_reference','duplicate','workload','access_sequence','weekly_activity_access',
    'planned_start','dependency','occupancy','possession_mix','closure','buffer','live_opposite_bound','live_interchange',
    'capacity','weekly_allocation','workfront','eclo','eclo_window','planned_date','results_consistency'])
def test_hard_rule_mutations(family):
    ds,rows=fixture(); a=ds['tables']['activity_details'][0]; p=ds['tables']['project_details'][0]; r=rows['SCHEDULE_ACCESS.csv'][0]; scenario='A'
    if family=='schema': r['week']='1.2'
    elif family=='unknown_reference': r['activity_id']='UNKNOWN'
    elif family=='duplicate': rows['SCHEDULE_ACCESS.csv'].append(dict(r))
    elif family=='workload': a['total_accesses']=2
    elif family=='access_sequence': r['access_seq']=2
    elif family=='weekly_activity_access': rows['SCHEDULE_ACCESS.csv'].append({**r,'access_seq':2})
    elif family=='planned_start': a['planned_start_week']=2
    elif family=='dependency': a['predecessor_activity_id']='T1'; ds['tables']['activity_details'].append({**a,'activity_id':'T1','predecessor_activity_id':''})
    elif family=='occupancy': rows['SCHEDULE_OCCUPANCY.csv'].pop()
    elif family in ('possession_mix','closure','buffer','live_opposite_bound','live_interchange','workfront'):
        ds,rows=fixture(n=2); a,b=ds['tables']['activity_details']; p=ds['tables']['project_details'][0]
        if family in ('possession_mix','closure'): p['access_type']='PM'
        if family=='buffer':
            p['nature_of_activity']='Non-live (Consist)'; b['start_location_id']=b['end_location_id']='SEC:ALP:S03_S04:EB'
        if family=='live_opposite_bound':
            p['nature_of_activity']='Live'; b['start_location_id']=b['end_location_id']='SEC:ALP:S01_S02:WB'
        if family=='live_interchange':
            p['nature_of_activity']='Live'; a['start_location_id']=a['end_location_id']='SEC:ALP:H01_H02:EB'; b['start_location_id']=b['end_location_id']='SEC:BET:H01_H02:EB'
        if family=='workfront':
            p['number_of_workfronts']=1; rows['SCHEDULE_ACCESS.csv'][1]['access_night']=1
        refresh(ds,rows)
    elif family=='capacity':
        for loc in ds['tables']['location_supply']: loc['supply_capacity']=0
    elif family=='weekly_allocation': r['access_night']=4
    elif family=='eclo': r['eclo']=1
    elif family=='eclo_window':
        scenario='C'; r['eclo']=1; rows['SCHEDULE_ACCESS.csv'].append({**r,'access_seq':2,'week':3}); refresh(ds,rows,scenario)
    elif family=='planned_date':
        scenario='B'; r['week']=2; refresh(ds,rows,scenario)
    elif family=='results_consistency': rows['RESULTS.csv'][0]['overrun_days']=1
    nights = {(r['activity_id'],r['week']):1 for r in rows['SCHEDULE_ACCESS.csv']} if family in ('closure','buffer','live_opposite_bound','live_interchange') else None
    assert family in codes(ds,rows,scenario,nights)

@pytest.mark.parametrize('scenario,excess,hard',[('A',1,True),('B',1,False),('B',2,False),('C',1,False),('C',2,True)])
def test_capacity_policies(scenario,excess,hard):
    ds,rows=fixture(n=excess)
    for loc in ds['tables']['location_supply']: loc['supply_capacity']=0
    for row in rows['SCHEDULE_OCCUPANCY.csv']: row['co_share_group']=row['activity_id']
    for row in rows['RESULTS.csv']: row['scenario']=scenario
    r=validate(ds,encode(rows),scenario)
    assert ('capacity' in {v['rule_code'] for v in r['hard_violations']})==hard
    assert r['objective_components']['excess_access_nights_total']==3*excess

@pytest.mark.parametrize('tier,priority,expected',[(1,1,'910.00'),(1,2,'840.00'),(1,3,'700.00'),(2,1,'91.00'),(2,2,'84.00'),(2,3,'70.00'),(3,1,'9.10'),(3,2,'8.40'),(3,3,'7.00')])
def test_priority_objective(tier,priority,expected):
    ds,rows=fixture(week=2); ds['tables']['project_details'][0]['contract_priority']=tier
    ds['tables']['activity_details'][0]['activity_priority']=priority
    r=validate(ds,encode(rows),'A')
    assert r['feasible'] and r['objective_score']==expected

@pytest.mark.parametrize('scenario,expected',[('A',None),('B','26.00'),('C','26.00')])
def test_eclo_decimal_and_combined_score(scenario,expected):
    ds,rows=fixture(); ds['tables']['activity_details'][0]['total_accesses']=1
    rows['SCHEDULE_ACCESS.csv'][0]['eclo']=1
    for row in rows['RESULTS.csv']: row['scenario']=scenario
    for loc in ds['tables']['location_supply']: loc['supply_capacity']=0
    r=validate(ds,encode(rows),scenario)
    assert r['objective_score']==expected
    assert r['completeness']['activities'][0]['delivered']=='1.5'
    assert r['completeness']['activities'][0]['over_delivery']=='0.5'
    assert r['warnings'][0]['code']=='over_delivery'

def test_two_eclo_nights_deliver_three_units():
    ds,rows=fixture(work=3); rows['SCHEDULE_ACCESS.csv'][0]['eclo']=1
    rows['SCHEDULE_ACCESS.csv'].append({**rows['SCHEDULE_ACCESS.csv'][0],'week':2,'access_seq':2})
    refresh(ds,rows,'C'); r=validate(ds,encode(rows),'C')
    assert r['completeness']['workload_gate_passed']
    assert r['objective_score']=='17.00'

def test_co_sharing_capacity_does_not_reduce_work():
    ds,rows=fixture(n=2,nature='Non-live (Consist)')
    r=validate(ds,encode(rows),'A')
    assert r['feasible'] and r['completeness']['activities_complete']==2
    assert not r['capacity_hotspots']

def test_access_nights_are_contract_local():
    ds,rows=fixture(n=2); a,b=ds['tables']['activity_details']; p=ds['tables']['project_details'][0]
    p['number_of_workfronts']=1
    ds['tables']['project_details'].append({**p,'contract_number':'OTHER'})
    b['contract_number']='OTHER'; rows['SCHEDULE_ACCESS.csv'][1]['access_night']=1
    refresh(ds,rows); assert 'workfront' not in codes(ds,rows)

@pytest.mark.parametrize('bad',['','-1','1.0','NaN','1e2','+1','  ','１２','99999999999999999999999'])
def test_invalid_integer_inputs(bad):
    ds,rows=fixture(); rows['SCHEDULE_ACCESS.csv'][0]['week']=bad
    assert 'schema' in codes(ds,rows)

@pytest.mark.parametrize('bad',['2','true','-1','1.5'])
def test_invalid_eclo_inputs(bad):
    ds,rows=fixture(); rows['SCHEDULE_ACCESS.csv'][0]['eclo']=bad
    assert 'schema' in codes(ds,rows)

@pytest.mark.parametrize('bad',['2027-02-30','20270110','2027-1-10','01/10/2027','not-date'])
def test_invalid_result_dates(bad):
    ds,rows=fixture(); rows['RESULTS.csv'][0]['simulated_completion_date']=bad
    assert 'schema' in codes(ds,rows)

@pytest.mark.parametrize('name',list(HEADERS))
def test_exact_headers_and_missing_files(name):
    ds,rows=fixture(); files=encode(rows); files[name]='extra,'+files[name]
    assert 'schema' in {v['rule_code'] for v in validate(ds,files,'A')['hard_violations']}
    del files[name]
    assert not validate(ds,files,'A')['feasible']

def test_mixed_scenarios_and_duplicate_results():
    ds,rows=fixture(); rows['RESULTS.csv'].append({**rows['RESULTS.csv'][0],'scenario':'B'})
    assert 'schema' in codes(ds,rows)
    rows['RESULTS.csv'][1]['scenario']='A'
    assert {'duplicate','results_consistency'}<=codes(ds,rows)

def test_missing_and_unexpected_occupancy_and_duplicate():
    ds,rows=fixture(); rows['SCHEDULE_OCCUPANCY.csv'].append({**rows['SCHEDULE_OCCUPANCY.csv'][0],'location_id':'PLAT:BET:S18:EB'})
    rows['SCHEDULE_OCCUPANCY.csv'].append(dict(rows['SCHEDULE_OCCUPANCY.csv'][0]))
    assert {'occupancy','duplicate'}<=codes(ds,rows)

def test_bounds_and_raw_csv_size():
    ds,rows=fixture(); files=encode(rows); files['SCHEDULE_ACCESS.csv']='x'*(POLICY.max_bytes+1)
    assert validate(ds,files,'A')['validation_status']=='invalid_submission'
    rows['SCHEDULE_ACCESS.csv'][0]['week']=31
    assert 'schema' in codes(ds,rows)

def test_row_limit():
    ds,rows=fixture(); files=encode(rows)
    files['RESULTS.csv']=HEADERS['RESULTS.csv']+'\n'+('A,C006,2027-01-10,0\n'*(POLICY.max_rows_per_file+1))
    assert validate(ds,files,'A')['validation_status']=='invalid_submission'

def test_preview_without_database_or_auth(monkeypatch):
    monkeypatch.delenv('DATABASE_URL',raising=False); monkeypatch.delenv('RAILPLAN_DEMO_AUTH',raising=False)
    with TestClient(app) as client:
        r=client.post('/api/ps1/validate',json={'instance_files':load_files(),'scenario':'A','files':sample_files()})
        assert r.status_code==200,r.text
        assert r.json()['hard_violations']==[]
        assert len(r.json()['warnings'])==70
        assert r.json()['objective_score']=='48.30'
        invalid=client.post('/api/ps1/validate',json={'scenario':'D'})
        assert invalid.status_code==422 and invalid.json()['error']['code']=='INVALID_INPUT'

def test_source_fingerprint_preserves_exact_text():
    ds=parse_instance(load_files()); files=sample_files(); r=validate(ds,files,'A')
    files['RESULTS.csv']=files['RESULTS.csv'].replace('\n','\r\n')
    changed=validate(ds,files,'A')
    assert changed['submission_fingerprint']!=r['submission_fingerprint']
    assert changed['hard_violations']==r['hard_violations']

def test_malformed_csv_never_executes():
    ds,rows=fixture(); files=encode(rows)
    files['SCHEDULE_ACCESS.csv']=HEADERS['SCHEDULE_ACCESS.csv']+'\n"unterminated'
    assert validate(ds,files,'A')['validation_status']=='invalid_submission'
    rows['SCHEDULE_ACCESS.csv'][0]['activity_id']='=HYPERLINK("evil")'
    assert 'unknown_reference' in codes(ds,rows)

def test_buffer_only_overlap_is_detected():
    ds,rows=fixture(n=2,nature='Non-live (Consist)'); b=ds['tables']['activity_details'][1]
    b['start_location_id']=b['end_location_id']='SEC:ALP:S04_H01:EB'
    refresh(ds,rows)
    assert 'buffer' in codes(ds,rows,physical_nights={('T0',1):1,('T1',1):1})

def test_explicit_nights_and_local_labels():
    ds,rows=fixture(n=2,nature='Non-live (Consist)')
    ds['tables']['activity_details'][1]['start_location_id']='SEC:ALP:S03_S04:EB'
    ds['tables']['activity_details'][1]['end_location_id']='SEC:ALP:S03_S04:EB'
    p=ds['tables']['project_details'][0]
    ds['tables']['project_details'].append({**p,'contract_number':'OTHER'})
    ds['tables']['activity_details'][1]['contract_number']='OTHER'
    rows['SCHEDULE_ACCESS.csv'][1]['access_night']=1
    refresh(ds,rows)
    files=encode(rows)
    csv_report=validate(ds,files,'A')
    assert csv_report['feasible'] and not csv_report['physical_validation_complete']
    assert csv_report['warnings'][0]['candidate_collision_type']=='buffer'
    same=validate(ds,files,'A',{('T0',1):1,('T1',1):1})
    assert not same['feasible'] and same['physical_validation_complete']
    assert 'buffer' in {v['rule_code'] for v in same['hard_violations']}
    different=validate(ds,files,'A',{('T0',1):1,('T1',1):2})
    assert different['feasible'] and different['physical_validation_complete']
    assert different['warnings']==[]
    assert same['submission_fingerprint']!=different['submission_fingerprint']
    assert same==validate(ds,files,'A',{('T1',1):1,('T0',1):1})

@pytest.mark.parametrize('mapping',[{}, {('T0',1):True}, {('T0',1):0},
    {('T0',1):1.5}, {'T0':1}, {('T0',1):1,('UNKNOWN',1):2}, []])
def test_invalid_physical_nights_fail_closed(mapping):
    ds,rows=fixture()
    report=validate(ds,encode(rows),'A',mapping)
    assert report['validation_status']=='invalid_submission'
    assert report['objective_score'] is None
    assert not report['physical_validation_complete']

def test_rich_legal_sharing_and_separate_possession_collision():
    ds,rows=fixture(n=2,nature='Non-live (Consist)')
    nights={('T0',1):1,('T1',1):1}
    assert validate(ds,encode(rows),'A',nights)['feasible']
    assert validate(ds,encode(rows),'A',{('T0',1):1,('T1',1):2})['validation_status']=='invalid_submission'
    for row in rows['SCHEDULE_OCCUPANCY.csv']:
        row['co_share_group']=row['activity_id']
    assert 'closure' in codes(ds,rows,physical_nights=nights)

def test_separate_nonlive_bounds_and_lines_never_merge_capacity():
    ds,rows=fixture(n=2); a,b=ds['tables']['activity_details']
    a['start_location_id']=a['end_location_id']='SEC:ALP:H01_H02:EB'
    b['start_location_id']=b['end_location_id']='SEC:BET:H01_H02:EB'
    refresh(ds,rows); r=validate(ds,encode(rows),'A')
    assert r['feasible']
    assert len(r['capacity_hotspots'])==6 and all(h['used']==1 for h in r['capacity_hotspots'])

@pytest.mark.parametrize('types,valid',[
 (['PM'],True),(['PC'],True),(['C'],True),(['C']*4,True),(['PC']+['C']*3,True),
 (['PM','C'],False),(['PM','PC'],False),(['PM','PM'],False),(['PC','PC'],False),
 (['C']*5,False),(['PC']+['C']*4,False)])
def test_possession_mixes_in_full_report(types,valid):
    ds,rows=fixture(n=len(types)); template=ds['tables']['project_details'][0]
    ds['tables']['project_details']=[]
    for index,kind in enumerate(types):
        contract=f'C{index}'
        ds['tables']['project_details'].append({**template,'contract_number':contract,'access_type':kind})
        ds['tables']['activity_details'][index]['contract_number']=contract
        rows['SCHEDULE_ACCESS.csv'][index]['access_night']=1
    refresh(ds,rows)
    assert ('possession_mix' not in codes(ds,rows))==valid

@pytest.mark.parametrize('scenario',['B','C'])
def test_independent_eclo_windows_per_line(scenario):
    ds,rows=fixture(n=2); a,b=ds['tables']['activity_details']
    b['start_location_id']=b['end_location_id']='SEC:BET:S11_S12:EB'
    rows['SCHEDULE_ACCESS.csv'][0]['eclo']=1
    rows['SCHEDULE_ACCESS.csv'][1].update(eclo=1,week=4)
    refresh(ds,rows,scenario)
    assert 'eclo_window' not in codes(ds,rows,scenario)

def test_crossline_live_must_fit_both_eclo_windows():
    ds,rows=fixture(n=2,nature='Live'); a,b=ds['tables']['activity_details']
    a['start_location_id']=a['end_location_id']='SEC:ALP:H01_H02:EB'
    b['start_location_id']=b['end_location_id']='SEC:BET:S11_S12:EB'
    rows['SCHEDULE_ACCESS.csv'][0]['eclo']=1
    rows['SCHEDULE_ACCESS.csv'][1].update(eclo=1,week=4)
    refresh(ds,rows,'C')
    r=validate(ds,encode(rows),'C')
    windows=[v for v in r['hard_violations'] if v['rule_code']=='eclo_window']
    assert len(windows)==1 and windows[0]['evidence']['line']=='BET'
    for row in rows['RESULTS.csv']:row['scenario']='B'
    assert 'eclo_window' not in codes(ds,rows,'B')

def test_dependency_allows_only_following_week():
    ds,rows=fixture(n=2); ds['tables']['activity_details'][1]['predecessor_activity_id']='T0'
    assert 'dependency' in codes(ds,rows)
    rows['SCHEDULE_ACCESS.csv'][1]['week']=2; refresh(ds,rows)
    assert 'dependency' not in codes(ds,rows)

def test_missing_result_unknown_contract_and_incomplete_result():
    ds,rows=fixture(); rows['RESULTS.csv'][0]['contract_number']='UNKNOWN'
    assert {'results_consistency','unknown_reference'}<=codes(ds,rows)
    ds['tables']['activity_details'][0]['total_accesses']=2
    refresh(ds,rows)
    assert {'workload','results_consistency'}<=codes(ds,rows)

def test_result_policy_does_not_pick_arbitrary_contract_type():
    ds,rows=fixture(); p=ds['tables']['project_details'][0]
    ds['tables']['project_details'].append({**p,'activity_type':'Other','planned_completion_date':'2027-02-01'})
    assert 'results_consistency' in codes(ds,rows)

def test_duplicate_occupancy_cannot_hide_supply():
    ds,rows=fixture(); rows['SCHEDULE_OCCUPANCY.csv'].append(dict(rows['SCHEDULE_OCCUPANCY.csv'][0]))
    for loc in ds['tables']['location_supply']:loc['supply_capacity']=0
    r=validate(ds,encode(rows),'B')
    assert r['objective_components']['excess_access_nights_total']==3
    assert not r['feasible']

def test_wire_upload_limit(monkeypatch):
    monkeypatch.delenv('DATABASE_URL',raising=False)
    with TestClient(app) as client:
        response=client.post('/api/ps1/validate',content=b' ' * 10_000_001,headers={'Content-Type':'application/json'})
        assert response.status_code==413 and response.json()['error']['code']=='PAYLOAD_TOO_LARGE'

def test_resource_budget_fails_closed():
    ds,rows=fixture(n=202)
    r=validate(ds,encode(rows),'A')
    assert r['validation_status']=='invalid_submission' and r['objective_score'] is None
    assert any(v['evidence'].get('physical_evaluation_complete') is False for v in r['hard_violations'])

def test_violation_structure_and_policy_are_stable():
    ds=parse_instance(load_files()); r=validate(ds,sample_files(),'A')
    assert all(set(v)=={'rule_code','message','week','activity_ids','contract_ids','location_ids','possession_group','evidence'} for v in r['hard_violations'])
    assert all(v['contract_ids'] and v['activity_ids'] and v['location_ids'] and v['possession_group'] for v in r['hard_violations'])
    r['rule_policy']['version']='tampered'
    assert validate(ds,sample_files(),'A')['rule_policy']['version']==POLICY.version

@pytest.mark.parametrize('row',['T0,1,1,0,1,extra','T0,1,1,0','T0,1,1,0,1\x00'])
def test_malformed_row_column_counts(row):
    ds,rows=fixture(); files=encode(rows); files['SCHEDULE_ACCESS.csv']=HEADERS['SCHEDULE_ACCESS.csv']+'\n'+row+'\n'
    assert validate(ds,files,'A')['validation_status']=='invalid_submission'
