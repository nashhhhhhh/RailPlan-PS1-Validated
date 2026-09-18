"""PS1 input contract. Weekly fictional topology is distinct from MRT demo data.

Imports are lossless CSV snapshots plus typed records. This module validates
instance structure, not schedule feasibility or the judges' objective score.
"""
import csv
import io
import json
import re
from collections import Counter
from datetime import date, timedelta
from hashlib import sha256
from pathlib import Path

FORMAT_VERSION = "ps1-instance/1"
HEADERS = {
 "01_LINES.csv":"line_code,line_name",
 "02_STATIONS.csv":"station_id,line_code,seq,is_interchange",
 "03_SECTORS.csv":"sector_id,line_code,from_station_id,to_station_id,seq,is_shared",
 "04_LOCATION_SUPPLY.csv":"location_id,location_kind,line_code,bound,supply_capacity",
 "05_BUFFER_LOCATION.csv":"nature_of_works,up_to_buffer_sectors,opposite_bound_required",
 "06_PARAMETERS.csv":"key,value",
 "07_PROJECT_DETAILS.csv":"contract_number,contract_description,contract_award_date,activity_type,nature_of_activity,contract_priority,contract_completion_date,planned_completion_date,number_of_workfronts,access_type,number_of_maximum_access_per_week",
 "08_ACTIVITY_DETAILS.csv":"activity_id,contract_number,activity_type,start_location_id,end_location_id,total_accesses,planned_start_date,predecessor_activity_id,activity_priority",
}
SCENARIOS = {
 "A":{"name":"Strict supply", "allow_eclo":False, "excess_capacity_limit":0, "planned_deadline_hard":False,
      "objective":"priority_weighted_overrun"},
 "B":{"name":"Strict schedule", "allow_eclo":True, "excess_capacity_limit":None, "planned_deadline_hard":True,
      "objective":"7 * excess_access_nights + 5 * eclo_nights"},
 "C":{"name":"Balanced", "allow_eclo":True, "excess_capacity_limit":1, "planned_deadline_hard":False,
      "eclo_window_weeks_per_line":2,
      "objective":"priority_weighted_overrun + 7 * excess_access_nights + 5 * eclo_nights"},
}

class InstanceError(ValueError): pass

def fail(message): raise InstanceError(message)

def integer(row, key, minimum=0, maximum=100000):
    value=row[key]
    if not re.fullmatch(r"\d+",value) or not minimum<=int(value)<=maximum:
        fail(f"{key}: expected integer {minimum}..{maximum}, got {value!r}")
    row[key]=int(value)

def iso_date(row,key):
    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}",row[key]):raise ValueError()
        return date.fromisoformat(row[key])
    except ValueError: fail(f"{key}: invalid ISO date {row[key]!r}")

def unique(rows, keys, label):
    result={}
    for row in rows:
        key=tuple(row[k] for k in keys)
        if key in result:fail(f"Duplicate {label}: {key}")
        result[key]=row
    return result

def load_files(directory=None):
    directory=Path(directory) if directory else Path(__file__).resolve().parents[1]/"data/PS1/01_data"
    return {name:(directory/name).read_text(encoding="utf-8-sig") for name in HEADERS}

def parse_instance(files):
    if set(files)!=set(HEADERS):
        fail(f"Supply exactly the eight input CSVs. Missing: {sorted(set(HEADERS)-set(files))}; unexpected: {sorted(set(files)-set(HEADERS))}")
    if sum(len(v.encode('utf-8')) for v in files.values())>4_000_000:fail("Instance exceeds 4 MB")
    tables={}
    for filename, header in HEADERS.items():
        try:
            reader=csv.DictReader(io.StringIO(files[filename].lstrip('\ufeff')),strict=True)
            if reader.fieldnames!=header.split(','):fail(f"{filename}: expected header {header}")
            rows=[]
            for number,row in enumerate(reader,2):
                if number>20001:fail(f"{filename}: exceeds 20000 rows")
                if None in row or any(v is None for v in row.values()):fail(f"{filename}:{number}: column count mismatch")
                row={k:v.strip() for k,v in row.items()}
                if any('\x00' in v or len(v)>4000 for v in row.values()):fail(f"{filename}:{number}: invalid cell")
                if any(not v for k,v in row.items() if k!='predecessor_activity_id'):fail(f"{filename}:{number}: required value missing")
                rows.append(row)
        except csv.Error as exc:fail(f"{filename}: malformed CSV: {exc}")
        if not rows:fail(f"{filename}: no records")
        tables[filename[3:-4].lower()]=rows
    lines=unique(tables['lines'],['line_code'],'line')
    if set(lines)!={('ALP',),('BET',)}:fail("PS1 requires ALP and BET lines")
    stations=tables['stations'];sectors=tables['sectors'];supply=tables['location_supply']
    for row in stations:
        integer(row,'seq',1);integer(row,'is_interchange',0,1)
        if (row['line_code'],) not in lines:fail("Unknown station line")
    station_map=unique(stations,['line_code','station_id'],'station per line')
    unique(stations,['line_code','seq'],'station sequence')
    for line in ('ALP','BET'):
        seq=sorted(r['seq'] for r in stations if r['line_code']==line)
        if seq!=list(range(1,11)):fail(f"{line}: expected ten contiguous station positions")
    for hub in ('H01','H02'):
        if any(not station_map.get((line,hub),{}).get('is_interchange') for line in ('ALP','BET')):
            fail(f"{hub}: expected interchange on both lines")
    for row in sectors:
        integer(row,'seq',1);integer(row,'is_shared',0,1)
        a=station_map.get((row['line_code'],row['from_station_id']))
        b=station_map.get((row['line_code'],row['to_station_id']))
        if not a or not b or b['seq']!=a['seq']+1:fail("Sector must connect adjacent ordered stations")
        if row['sector_id']!=f"SEC:{row['line_code']}:{row['from_station_id']}_{row['to_station_id']}":fail("Sector ID does not match its endpoints")
        if row['is_shared']:fail("PS1 tunnel capacity is independent per line; is_shared must be zero")
    sector_map={r['sector_id']:r for r in sectors}
    unique(sectors,['sector_id'],'sector');unique(sectors,['line_code','seq'],'sector sequence')
    for line in ('ALP','BET'):
        endpoints=[station_map[(line,r['from_station_id'])]['seq'] for r in sectors if r['line_code']==line]
        if sorted(endpoints)!=list(range(1,10)):fail(f"{line}: incomplete tunnel chain")
    expected={f"{r['sector_id']}:{b}":('tunnel sector',r['line_code'],b) for r in sectors for b in ('EB','WB')}
    expected.update({f"PLAT:{r['line_code']}:{r['station_id']}:{b}":('platform sector',r['line_code'],b) for r in stations for b in ('EB','WB')})
    locations=unique(supply,['location_id'],'supply location')
    if {k[0] for k in locations}!=set(expected):fail("Supply must contain every tunnel and platform location on both bounds")
    for row in supply:
        integer(row,'supply_capacity',0,1000)
        if (row['location_kind'],row['line_code'],row['bound'])!=expected[row['location_id']]:fail(f"Location metadata mismatch: {row['location_id']}")
    buffers=tables['buffer_location']
    unique(buffers,['nature_of_works'],'buffer rule')
    for row in buffers:
        integer(row,'up_to_buffer_sectors',0,10);integer(row,'opposite_bound_required',0,1)
    required={'Live':(2,1),'Non-live (Consist)':(1,0),'Non-live (Others)':(0,0)}
    if {r['nature_of_works']:(r['up_to_buffer_sectors'],r['opposite_bound_required']) for r in buffers}!=required:
        fail("Buffer definitions differ from the published PS1 rules")
    unique(tables['parameters'],['key'],'parameter')
    params={r['key']:r['value'] for r in tables['parameters']}
    if set(params)!={'horizon_start','horizon_weeks'}:fail("Expected horizon_start and horizon_weeks parameters")
    start=iso_date(params,'horizon_start');integer(params,'horizon_weeks',1,520)
    if start.weekday()!=0:fail("horizon_start must be a Monday")
    projects=tables['project_details'];activities=tables['activity_details']
    project_map=unique(projects,['contract_number','activity_type'],'contract/type')
    for p in projects:
        integer(p,'contract_priority',1,3);integer(p,'number_of_workfronts',1,1000);integer(p,'number_of_maximum_access_per_week',1,7)
        for key in ('contract_award_date','contract_completion_date','planned_completion_date'):iso_date(p,key)
        if p['access_type'] not in ('PM','PC','C'):fail("Unknown possession access type")
        if p['nature_of_activity'] not in required:fail("Unknown nature_of_activity")
        if p['number_of_maximum_access_per_week']!=(2 if p['nature_of_activity']=='Live' else 3):fail("Weekly access cap differs from PS1 contract rule")
    activity_map=unique(activities,['activity_id'],'activity')
    warnings=[]
    for a in activities:
        integer(a,'total_accesses',1,100000);integer(a,'activity_priority',1,3)
        planned=iso_date(a,'planned_start_date')
        a['planned_start_week']=max(1,(planned-start).days//7+1)
        if a['planned_start_week']>params['horizon_weeks']:warnings.append(f"{a['activity_id']} starts beyond supplied planning horizon")
        p=project_map.get((a['contract_number'],a['activity_type']))
        if not p:fail(f"{a['activity_id']}: missing contract/type")
        first=locations.get((a['start_location_id'],));last=locations.get((a['end_location_id'],))
        if not first or not last:fail(f"{a['activity_id']}: unknown endpoint location")
        if (first['line_code'],first['bound'])!=(last['line_code'],last['bound']):fail("Activity endpoints must be on the same line and bound")
        # Alternating station/platform and tunnel positions preserve every traversed location.
        line,bound=first['line_code'],first['bound']
        chain=[]
        for station in sorted((r for r in stations if r['line_code']==line),key=lambda r:r['seq']):
            chain.append(f"PLAT:{line}:{station['station_id']}:{bound}")
            sector=next((s for s in sectors if s['line_code']==line and s['from_station_id']==station['station_id']),None)
            if sector:chain.append(f"{sector['sector_id']}:{bound}")
        lo,hi=sorted((chain.index(first['location_id']),chain.index(last['location_id'])))
        # Organiser sample includes book-in/book-out platforms for SEC endpoints.
        if chain[lo].startswith('SEC:'):lo-=1
        if chain[hi].startswith('SEC:'):hi+=1
        a['span_location_ids']=chain[lo:hi+1]
        a['line_code']=line;a['bound']=bound
        predecessor=a['predecessor_activity_id']
        if predecessor and (predecessor,) not in activity_map:fail(f"{a['activity_id']}: unknown predecessor {predecessor}")
    # Iterative traversal handles long hidden-instance chains without recursion limits.
    completed=set()
    for key in activity_map:
        current=key[0];trail=set()
        while current and current not in completed:
            if current in trail:fail(f"Dependency cycle at {current}")
            trail.add(current);current=activity_map[(current,)]['predecessor_activity_id']
        completed.update(trail)
    digest=sha256(json.dumps(files,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    summary={'lines':len(lines),'station_records':len(stations),'unique_station_ids':len({s['station_id'] for s in stations}),
      'tunnel_sectors':len(sectors),'locations':len(supply),'contracts':len({p['contract_number'] for p in projects}),
      'activities':len(activities),'total_access_workload':sum(a['total_accesses'] for a in activities),
      'dependencies':sum(bool(a['predecessor_activity_id']) for a in activities),
      'horizon_start':start.isoformat(),'horizon_weeks':params['horizon_weeks'],
      'horizon_end':(start+timedelta(weeks=params['horizon_weeks'],days=-1)).isoformat(),
      'weekly_supply_distribution':dict(sorted(Counter(str(s['supply_capacity']) for s in supply).items()))}
    return {'format_version':FORMAT_VERSION,'fingerprint':digest,'summary':summary,'tables':tables,
      'parameters':params,'scenario_policies':SCENARIOS,'warnings':warnings,
      'data_status':'valid_instance','schedule_status':'not_generated','judge_validation':'not_run',
      'span_semantics':'Inclusive tunnel span with book-in, intermediate and book-out platforms; buffers, opposite bound and Live interchange closures require the PS1 solver/validator.',
      'source':'Uploaded PS1 instance; fictional network, no geospatial coordinates'}
