"""Deterministic hard constraints, independent of storage and severity scoring."""
from collections import defaultdict, Counter
from decimal import Decimal, ROUND_HALF_UP
from itertools import combinations
from .contracts import POLICY, violation
from .network import chains, expand

def legal_mix(types):
    counts = Counter(types)
    return bool(types) and ((counts['PM']==1 and len(types)==1) or
        (counts['PM']==0 and counts['PC']<=1 and counts['C']<=4-counts['PC']))

def evaluate(dataset, tables, scenario, physical_nights: dict[tuple[str, int], int] | None = None):
    source = dataset['tables']
    activities = {a['activity_id']: a for a in source['activity_details']}
    projects = {(p['contract_number'],p['activity_type']):p for p in source['project_details']}
    supply = {r['location_id']:r['supply_capacity'] for r in source['location_supply']}
    violations, warnings = [], []
    def add(code, message, ids=(), **kw):
        contracts = kw.pop('contracts', [])
        contracts = set(contracts) | {activities[i]['contract_number'] for i in ids if i in activities}
        violations.append(violation(code, message, activities=ids, contracts=contracts, **kw))
    def project(aid):
        a=activities[aid]
        return projects[a['contract_number'],a['activity_type']]
    network = chains(dataset)
    spans = {aid:expand(a,project(aid),network) for aid,a in sorted(activities.items())}
    access = []
    # Duplicate logical accesses are all excluded, avoiding row-order-dependent credit.
    counts = Counter((r['activity_id'],r['access_seq']) for r in tables['SCHEDULE_ACCESS.csv'])
    for row in tables['SCHEDULE_ACCESS.csv']:
        aid=row['activity_id']
        if aid not in activities:
            add('unknown_reference','Unknown access activity',[aid],week=row['week'],row=row)
        elif row['week']>dataset['parameters']['horizon_weeks']:
            add('schema','Access week is outside planning horizon',[aid],week=row['week'],row=row)
        elif counts[aid,row['access_seq']]==1:
            access.append(row)
    access.sort(key=lambda r:(r['activity_id'],r['week'],r['access_seq']))
    by_activity, by_week = defaultdict(list), defaultdict(list)
    for r in access:
        by_activity[r['activity_id']].append(r)
        by_week[r['week']].append(r)
    workload, completion_weeks = [], {}
    for aid,a in sorted(activities.items()):
        rows=by_activity[aid]
        delivered=sum((Decimal('1.5') if r['eclo'] else Decimal('1.0') for r in rows),Decimal(0))
        standard=sum((Decimal('1.0') for r in rows if not r['eclo']),Decimal(0))
        eclo=sum((Decimal('1.5') for r in rows if r['eclo']),Decimal(0))
        required=Decimal(a['total_accesses'])
        complete=delivered>=required
        workload.append({'activity_id':aid,'contract_number':a['contract_number'],
            'required':str(required.quantize(Decimal('0.1'),rounding=ROUND_HALF_UP)),
            'delivered':str(delivered.quantize(Decimal('0.1'),rounding=ROUND_HALF_UP)),
            'standard_access_contribution':str(standard.quantize(Decimal('0.1'),rounding=ROUND_HALF_UP)),
            'eclo_contribution':str(eclo.quantize(Decimal('0.1'),rounding=ROUND_HALF_UP)),
            'shortfall':str(max(Decimal(0),required-delivered).quantize(Decimal('0.1'),rounding=ROUND_HALF_UP)),
            'over_delivery':str(max(Decimal(0),delivered-required).quantize(Decimal('0.1'),rounding=ROUND_HALF_UP)),
            'present':bool(rows),'complete':complete})
        if not complete:
            add('workload','Activity workload not fully delivered',[aid],required=str(required),delivered=str(delivered))
        if delivered>required:
            warnings.append({'code':'over_delivery','activity_id':aid,'extra_work_units':str(delivered-required)})
        if complete and rows: completion_weeks[aid]=max(r['week'] for r in rows)
        if [r['access_seq'] for r in rows]!=list(range(1,len(rows)+1)):
            add('access_sequence','Access sequences must be continuous from 1 in chronological order',[aid],sequences=[r['access_seq'] for r in rows])
        for week,count in sorted(Counter(r['week'] for r in rows).items()):
            if count>1: add('weekly_activity_access','At most one access per activity per week',[aid],week=week,count=count)
        for r in rows:
            if r['week']<a['planned_start_week']:
                add('planned_start','Access precedes planned start week',[aid],week=r['week'],planned_start_week=a['planned_start_week'])
            if scenario=='A' and r['eclo']:
                add('eclo','Scenario A forbids ECLO',[aid],week=r['week'],access_seq=r['access_seq'])
    for aid,a in sorted(activities.items()):
        pred=a['predecessor_activity_id']
        if pred and by_activity[aid]:
            first=min(r['week'] for r in by_activity[aid])
            if pred not in completion_weeks or first<=completion_weeks[pred]:
                add('dependency','Successor must start after full predecessor completion',[pred,aid],week=first,predecessor_completion_week=completion_weeks.get(pred))
    # Canonical location sets drive all checks, including missing CSV occupancy.
    expected={(r['activity_id'],r['week'],loc) for r in access for loc in spans[r['activity_id']]['occupied']}
    provided=defaultdict(list)
    for r in tables['SCHEDULE_OCCUPANCY.csv']:
        aid,loc,week=r['activity_id'],r['location_id'],r['week']
        if aid not in activities or loc not in supply:
            add('unknown_reference','Unknown occupancy activity or location',[aid],week=week,locations=[loc],row=r)
        provided[aid,week,loc].append(r['co_share_group'])
    for key in sorted(expected-set(provided)):
        aid,week,loc=key
        add('occupancy','Required canonical location is missing',[aid],week=week,locations=[loc],kind='missing')
    for key in sorted(set(provided)-expected):
        aid,week,loc=key
        add('occupancy','Unexpected occupancy location or unscheduled activity/week',[aid],week=week,locations=[loc],kind='unexpected')
    groups=defaultdict(set)
    assignment={}
    for aid,week,loc in sorted(expected):
        labels=provided.get((aid,week,loc),[])
        # Tagged tuple keeps synthetic values disjoint from arbitrary user labels.
        label=('submitted',labels[0]) if len(labels)==1 else ('missing_or_ambiguous',aid)
        assignment[aid,week,loc]=label
        groups[loc,week,label].add(aid)
    legal={}
    for (loc,week,label), ids in sorted(groups.items()):
        types=[project(aid)['access_type'] for aid in sorted(ids)]
        valid=legal_mix(types)
        legal[loc,week,label]=valid
        if not valid:
            add('possession_mix','Illegal possession mix',ids,week=week,locations=[loc],
                group={'location_id':loc,'week':week,'co_share_group':label[1]},types=types)
    weekly, fronts=defaultdict(list),defaultdict(list)
    for r in access:
        a=activities[r['activity_id']]
        key=(a['contract_number'],a['activity_type'],r['week'])
        weekly[key].append(r)
        fronts[key+(r['access_night'],)].append(r)
    for (contract,kind,week), rows in sorted(weekly.items()):
        cap=projects[contract,kind]['number_of_maximum_access_per_week']
        nights=sorted({r['access_night'] for r in rows})
        if len(nights)>cap or any(n>cap for n in nights):
            add('weekly_allocation','Contract/type weekly night allocation exceeded',[r['activity_id'] for r in rows],week=week,activity_type=kind,access_nights=nights,limit=cap)
    for (contract,kind,week,night),rows in sorted(fronts.items()):
        ids=sorted({r['activity_id'] for r in rows})
        cap=projects[contract,kind]['number_of_workfronts']
        if len(ids)>cap:
            add('workfront','Concurrent activities exceed workfront limit',ids,week=week,activity_type=kind,access_night=night,limit=cap)
    eclo_lines=defaultdict(list)
    for r in access:
        if r['eclo']:
            for line in sorted(spans[r['activity_id']]['lines']): eclo_lines[line].append(r)
    if scenario=='C':
        for line,rows in sorted(eclo_lines.items()):
            weeks=sorted({r['week'] for r in rows})
            if weeks[-1]-weeks[0]>1:
                add('eclo_window','ECLO exceeds two consecutive calendar weeks on line',[r['activity_id'] for r in rows],week=weeks[-1],line=line,weeks=weeks)
    # Explicit mappings must cover exactly the accepted activity/week keys.
    rich = physical_nights is not None
    night_map = {}
    alignment_valid = True
    physical_night_identity = []
    if rich:
        expected_nights = {(r['activity_id'], r['week']) for r in access}
        if not isinstance(physical_nights, dict):
            alignment_valid = False
        else:
            for key, value in physical_nights.items():
                if (not isinstance(key, tuple) or len(key) != 2
                        or not isinstance(key[0], str) or type(key[1]) is not int
                        or type(value) is not int or value < 1):
                    alignment_valid = False
                    continue
                night_map[key] = value
            alignment_valid = alignment_valid and set(night_map) == expected_nights
        physical_night_identity = [[aid, week, night] for (aid, week), night in sorted(night_map.items())]
        if not alignment_valid:
            add('schema', 'Physical-night mapping must contain exactly every scheduled activity/week with positive integer night IDs',
                physical_evaluation_complete=False)
        else:
            for (loc, week, label), ids in sorted(groups.items()):
                if len({night_map[aid, week] for aid in ids}) > 1:
                    alignment_valid = False
                    add('schema', 'One location/week possession group cannot span multiple physical nights',
                        ids, week=week, locations=[loc], physical_evaluation_complete=False)
    # CSV-only checks index candidate overlaps by week. Rich checks also index night.
    affected=defaultdict(set)
    for r in access:
        if rich and not alignment_valid:
            continue
        night = night_map[r['activity_id'],r['week']] if rich else None
        for loc in spans[r['activity_id']]['closure']: affected[r['week'],night,loc].add(r['activity_id'])
    pairs=set()
    limit_exceeded=False
    for (week,night,_),ids in sorted(affected.items()):
        for a,b in combinations(sorted(ids),2):
            pairs.add((week,a,b))
            if len(pairs)>POLICY.max_intersecting_pairs:
                limit_exceeded=True
                break
        if limit_exceeded: break
    if limit_exceeded:
        add('schema','Submission exceeds bounded intersecting-pair evaluation limit; physical evaluation not completed',
            limit=POLICY.max_intersecting_pairs,physical_evaluation_complete=False)
        pairs=set()
    for week,a,b in sorted(pairs):
        sa,sb=spans[a],spans[b]
        common=sa['occupied'] & sb['occupied']
        shared={loc for loc in common if assignment[a,week,loc]==assignment[b,week,loc]
                and legal[loc,week,assignment[a,week,loc]]}
        if scenario=='A' and common and shared==common:
            continue
        # Different local groups establish separate possession slots at that location only.
        same={loc for loc in common if assignment[a,week,loc]==assignment[b,week,loc]}-shared
        collisions={
            'closure':common-shared if rich else same,
            'buffer':(sa['buffer'] & (sb['occupied']|sb['buffer'])) | (sb['buffer'] & sa['occupied']),
            'live_opposite_bound':(sa['opposite'] & sb['closure']) | (sb['opposite'] & sa['closure']),
            'live_interchange':(sa['interchange'] & sb['closure']) | (sb['interchange'] & sa['closure']),
        }
        for code,locations in sorted(collisions.items()):
            if locations:
                if not rich:
                    warnings.append({'code':'physical_night_alignment_unverifiable',
                        'week':week,'activity_ids':[a,b],'candidate_collision_type':code,
                        'candidate_locations':sorted(locations),
                        'message':'Weekly footprints overlap, but the CSVs do not establish physical-night alignment. This is not proof of a conflict.'})
                    continue
                add(code,'Possession footprints conflict on the same explicit physical night',[a,b],week=week,locations=locations,
                    group={'assignments': [{'activity_id':aid,'location_id':loc,'co_share_group':assignment[aid,week,loc][1]}
                        for aid in (a,b) for loc in sorted(spans[aid]['occupied'])]},
                    alignment='explicit_physical_night',physical_night=night_map[a,week],shared_locations=sorted(shared))
    usage=defaultdict(list)
    for (loc,week,label),ids in sorted(groups.items()):
        usage[loc,week].append({'co_share_group':label[1],'source':label[0],'activity_ids':sorted(ids)})
    hotspots=[]
    for (loc,week),slots in sorted(usage.items()):
        used=len(slots); cap=supply[loc]; excess=max(0,used-cap)
        if used>=cap:
            hotspots.append({'location_id':loc,'week':week,'supply':cap,'used':used,'excess':excess,'possession_groups':slots})
        allowance={'A':0,'B':None,'C':1}[scenario]
        if allowance is not None and excess>allowance:
            add('capacity','Location/week exceeds scenario supply allowance',
                [aid for slot in slots for aid in slot['activity_ids']],week=week,locations=[loc],
                group={'groups':slots},supply=cap,used=used,excess=excess,allowance=allowance)
    return {'physical_validation_complete':rich and alignment_valid and not limit_exceeded,
            'physical_night_identity':physical_night_identity,
            'violations':violations,'warnings':warnings,'access':access,'completion_weeks':completion_weeks,
            'workload':workload,'capacity_hotspots':hotspots,'activities':activities,'projects':projects}
