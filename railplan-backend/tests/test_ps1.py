import csv
import io
from copy import deepcopy
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.ps1 import load_files,parse_instance,InstanceError

def change(files,name,field,value,row_number=0):
    rows=list(csv.DictReader(io.StringIO(files[name])))
    rows[row_number][field]=value
    stream=io.StringIO();writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    files[name]=stream.getvalue()
    return files

def test_public_instance_full_workload_and_hubs():
    data=parse_instance(load_files());s=data['summary']
    assert (s['activities'],s['contracts'],s['total_access_workload'])==(54,14,192)
    assert (s['station_records'],s['unique_station_ids'],s['locations'])==(20,18,76)
    assert s['horizon_start']=='2027-01-04' and s['horizon_weeks']==30
    assert data['schedule_status']=='not_generated' and data['judge_validation']=='not_run'
    assert len(data['tables']['activity_details'])==54

def test_every_span_matches_organiser_sample():
    data=parse_instance(load_files())
    file=Path(__file__).resolve().parents[1]/'data/PS1/03_submission_sample/SCHEDULE_OCCUPANCY.csv'
    with file.open() as stream:rows=list(csv.DictReader(stream))
    for activity in data['tables']['activity_details']:
        expected={r['location_id'] for r in rows if r['activity_id']==activity['activity_id']}
        assert set(activity['span_location_ids'])==expected,activity['activity_id']

def test_beta_sector_sequence_is_global_not_station_sequence():
    data=parse_instance(load_files())
    assert next(r for r in data['tables']['sectors'] if r['line_code']=='BET')['seq']==10
    a=next(a for a in data['tables']['activity_details'] if a['activity_id']=='A001')
    assert len(a['span_location_ids'])==5
    assert 'PLAT:BET:S15:EB' in a['span_location_ids']
    assert 'PLAT:BET:S17:EB' in a['span_location_ids']

@pytest.mark.parametrize('name,field,value',[
 ('08_ACTIVITY_DETAILS.csv','total_accesses','0'),
 ('08_ACTIVITY_DETAILS.csv','total_accesses','2.5'),
 ('08_ACTIVITY_DETAILS.csv','planned_start_date','2027-02-30'),
 ('08_ACTIVITY_DETAILS.csv','predecessor_activity_id','missing'),
 ('08_ACTIVITY_DETAILS.csv','predecessor_activity_id','A001'),
 ('08_ACTIVITY_DETAILS.csv','end_location_id','SEC:ALP:S01_S02:EB'),
 ('08_ACTIVITY_DETAILS.csv','contract_number','missing'),
 ('07_PROJECT_DETAILS.csv','access_type','UNKNOWN'),
 ('07_PROJECT_DETAILS.csv','contract_priority','4'),
 ('07_PROJECT_DETAILS.csv','number_of_maximum_access_per_week','7'),
 ('04_LOCATION_SUPPLY.csv','supply_capacity','-1'),
 ('03_SECTORS.csv','is_shared','1'),
 ('05_BUFFER_LOCATION.csv','up_to_buffer_sectors','0'),
])
def test_invalid_instances_rejected(name,field,value):
    with pytest.raises(InstanceError):parse_instance(change(load_files(),name,field,value))

def test_duplicate_activity_and_missing_file_rejected():
    files=load_files();name='08_ACTIVITY_DETAILS.csv'
    files[name]+='\n'+files[name].splitlines()[1]
    with pytest.raises(InstanceError,match='Duplicate'):parse_instance(files)
    files=load_files();del files['01_LINES.csv']
    with pytest.raises(InstanceError,match='eight'):parse_instance(files)

def test_two_activity_cycle_rejected():
    files=change(load_files(),'08_ACTIVITY_DETAILS.csv','predecessor_activity_id','A002')
    change(files,'08_ACTIVITY_DETAILS.csv','predecessor_activity_id','A001',1)
    with pytest.raises(InstanceError,match='cycle'):parse_instance(files)

def test_header_extra_column_and_oversized_rejected():
    files=load_files();files['01_LINES.csv']=files['01_LINES.csv'].replace('line_code','wrong')
    with pytest.raises(InstanceError,match='header'):parse_instance(files)
    files=load_files();files['01_LINES.csv']='x'*4_000_001
    with pytest.raises(InstanceError,match='4 MB'):parse_instance(files)

def test_hidden_instance_changes_are_not_replaced_by_sample():
    original=load_files();files=change(load_files(),'08_ACTIVITY_DETAILS.csv','total_accesses','9')
    result=parse_instance(files)
    assert result['summary']['total_access_workload']==199
    assert result['fingerprint']!=parse_instance(original)['fingerprint']

def test_stateless_preview_and_example_work_without_database(monkeypatch):
    monkeypatch.delenv('DATABASE_URL',raising=False)
    with TestClient(app) as client:
        response=client.get('/api/ps1/example')
        assert response.status_code==200
        result=client.post('/api/ps1/preview',json={'files':response.json()['files']})
        assert result.status_code==200 and result.json()['summary']['activities']==54
        bad=client.post('/api/ps1/preview',json={'files':{'01_LINES.csv':'bad'}})
        assert bad.status_code==422
        assert client.post('/api/ps1/instances',json={'files':load_files()}).status_code==503

def test_scenario_policies_are_not_the_legacy_risk_score():
    p=parse_instance(load_files())['scenario_policies']
    assert not p['A']['allow_eclo'] and p['A']['excess_capacity_limit']==0
    assert p['B']['planned_deadline_hard'] and p['B']['excess_capacity_limit'] is None
    assert p['C']['excess_capacity_limit']==1 and p['C']['eclo_window_weeks_per_line']==2
