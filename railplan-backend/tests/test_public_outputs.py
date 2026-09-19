"""Release-shape checks for RailPlan-generated organiser-dataset outputs."""
import csv
from datetime import date
from hashlib import sha256
import io
import json
from pathlib import Path

from app.ps1 import load_files, parse_instance


ROOT=Path(__file__).resolve().parents[2]
OUTPUT=ROOT/'competition-submission'
INPUT_HASHES={
    '01_LINES.csv':'69d47e99de632c08f09229b34d2642af74dba4b7a6b8870e41f853cae9793eaa',
    '02_STATIONS.csv':'9f9f44b6c2500a26cea9b3fa2c77ba957079ab5a01fd92d7c4d0be11296340d8',
    '03_SECTORS.csv':'4b30ddd5d31cd6abc1ab8cc152a08bbc68060e39d65a5242521593fa885efcec',
    '04_LOCATION_SUPPLY.csv':'d5e4bdfa8c4fb3116c83a7f53749e048f5c6c5963f0343c6d825b8120e62dc35',
    '05_BUFFER_LOCATION.csv':'2abb5e1daeafddbe73be60554d77c5e4ee544085bbcbb4d89d65c367f10dddf9',
    '06_PARAMETERS.csv':'5765599b4475e6f2fc9fc3226357dc826b5d4008817ae513701551e7803de7bd',
    '07_PROJECT_DETAILS.csv':'4949a7cb8826c3f234910b29988e8aa4ae9e4d6b7e6294f402a1506846ec33b8',
    '08_ACTIVITY_DETAILS.csv':'8f0a52bc6e062b98f1c980cdacabf5c4572f091ae127fc76f734e977d2201eb6',
}
SAMPLE_HASHES={
    'RESULTS.csv':'9eca188c07c21438f3b1adc03cb83bb7ec0264f0a816756f9293c565bbc0ae1a',
    'SCHEDULE_ACCESS.csv':'fb5c55cc8e01b19340bb52b20abc3c3ae558f11192facfa858c6d5de91677ff1',
    'SCHEDULE_OCCUPANCY.csv':'0a5a69c60cb57b5f553b716034c3ff017a1487ab570d7eb04b7323b4668e9c0d',
}
HEADERS={
    'SCHEDULE_ACCESS.csv':['activity_id','access_seq','week','eclo','access_night'],
    'SCHEDULE_OCCUPANCY.csv':['activity_id','week','location_id','co_share_group'],
    'RESULTS.csv':['scenario','contract_number','simulated_completion_date','overrun_days'],
}


def digest(path):return sha256(path.read_bytes()).hexdigest()


def test_organiser_inputs_and_samples_are_byte_identical():
    data=ROOT/'railplan-backend'/'data'/'PS1'/'01_data'
    sample=ROOT/'railplan-backend'/'data'/'PS1'/'03_submission_sample'
    assert {name:digest(data/name) for name in INPUT_HASHES}==INPUT_HASHES
    assert {name:digest(sample/name) for name in SAMPLE_HASHES}==SAMPLE_HASHES


def test_generated_outputs_have_exact_shape_order_and_evidence():
    activities={row['activity_id'] for row in parse_instance(load_files())['tables']['activity_details']}
    for scenario in 'ABC':
        directory=OUTPUT/f'scenario-{scenario.lower()}'
        assert sorted(path.name for path in directory.iterdir())==sorted(HEADERS)
        parsed={}
        for name,header in HEADERS.items():
            raw=(directory/name).read_bytes()
            assert b'\r' not in raw and raw.endswith(b'\n') and b'physical_night' not in raw
            reader=csv.DictReader(io.StringIO(raw.decode('utf-8')))
            assert reader.fieldnames==header
            parsed[name]=list(reader)
        access=parsed['SCHEDULE_ACCESS.csv']
        assert {row['activity_id'] for row in access}==activities
        assert access==sorted(access,key=lambda row:(row['activity_id'],int(row['access_seq'])))
        assert parsed['SCHEDULE_OCCUPANCY.csv']==sorted(parsed['SCHEDULE_OCCUPANCY.csv'],key=lambda row:(row['activity_id'],int(row['week']),row['location_id']))
        assert parsed['RESULTS.csv']==sorted(parsed['RESULTS.csv'],key=lambda row:row['contract_number'])
        assert all(row['scenario']==scenario and int(row['overrun_days'])>=0 and date.fromisoformat(row['simulated_completion_date']) for row in parsed['RESULTS.csv'])
        if scenario=='A':assert all(row['eclo']=='0' for row in access)
        evidence=json.loads((OUTPUT/'evidence'/f'scenario-{scenario.lower()}.json').read_text(encoding='utf-8'))
        assert evidence['scenario']==scenario and evidence['publishable'] is True
        assert evidence['physical_validation_complete'] is True and evidence['hard_violation_count']==0
        assert evidence['judge_validation']=='not_run' and evidence['score_verification']=='internal_only'


def test_generated_outputs_are_not_organiser_samples_and_checksums_verify():
    sample=ROOT/'railplan-backend'/'data'/'PS1'/'03_submission_sample'
    for scenario in 'abc':
        assert any(digest(OUTPUT/f'scenario-{scenario}'/name)!=digest(sample/name) for name in HEADERS)
    lines=(OUTPUT/'evidence'/'checksums.sha256').read_text(encoding='ascii').splitlines()
    for line in lines:
        expected,name=line.split('  ',1)
        assert digest(OUTPUT/Path(name))==expected
