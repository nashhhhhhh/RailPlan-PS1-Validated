"""Canonical footprints and reproducible incompatible-pair diagnostics."""
from itertools import combinations
from app.ps1_validation.network import chains, expand
from app.ps1_validation.rules import legal_mix

class InputError(ValueError):
    pass

def prepare(dataset, options, scenario='A'):
    tables = dataset['tables']
    activities = {a['activity_id']: a for a in sorted(tables['activity_details'], key=lambda a:a['activity_id'])}
    projects = {(p['contract_number'],p['activity_type']):p for p in sorted(tables['project_details'], key=lambda p:(p['contract_number'],p['activity_type']))}
    horizon = dataset['parameters']['horizon_weeks']
    diagnostics = []
    accesses=sum(a['total_accesses'] for a in activities.values())
    if len(activities)>200 or len(activities)*horizon*options.physical_nights_per_week > 50000 or accesses>2000 or accesses*horizon>60000:
        return {'limit': True, 'diagnostics':[{'code':'model_limit','message':'Model exceeds 200 activities, 50,000 presence slots, 2,000 accesses or 60,000 sequence/week slots; split/reduce the planning instance.'}]}
    for field in ('locked_placements','baseline_placements'):
        seen = set()
        for placement in getattr(options, field):
            a = activities.get(placement.activity_id)
            key = placement.activity_id, placement.access_seq
            if placement.co_share_group is not None:
                raise InputError(f'{field}: co_share_group cannot be locked on an access placement; lock physical_night to fix possession concurrency {key}')
            if key in seen: raise InputError(f'{field}: duplicate activity/access_seq {key}')
            seen.add(key)
            if not a or placement.access_seq > a['total_accesses']: raise InputError(f'{field}: unknown activity/access_seq {key}')
            p = projects[a['contract_number'],a['activity_type']]
            if placement.week > horizon or placement.physical_night > options.physical_nights_per_week:
                raise InputError(f'{field}: placement outside horizon/night domain {key}')
            if placement.access_night is not None and placement.access_night > p['number_of_maximum_access_per_week']:
                raise InputError(f'{field}: local access index exceeds allocation {key}')
    net = chains(dataset)
    footprints = {aid:expand(a,projects[a['contract_number'],a['activity_type']],net) for aid,a in activities.items()}
    supply = {r['location_id']:r['supply_capacity'] for r in tables['location_supply']}
    pairs = []
    for aid,bid in combinations(activities,2):
        a,b = footprints[aid],footprints[bid]
        kinds = [projects[activities[i]['contract_number'],activities[i]['activity_type']]['access_type'] for i in (aid,bid)]
        common_occupied=a['occupied'] & b['occupied']
        collisions = {
            # Compatibility does not establish a possession.  Keep the complete
            # collision footprint; the model may exempt it only by placing both
            # activities in the same valid, transitive possession slot.
            'closure':(a['occupied'] & b['closure']) | (b['occupied'] & a['closure']),
            'buffer':(a['buffer'] & (b['occupied']|b['buffer'])) | (b['buffer'] & a['occupied']),
            'live_opposite_bound':(a['opposite'] & b['closure']) | (b['opposite'] & a['closure']),
            'live_interchange':(a['interchange'] & b['closure']) | (b['interchange'] & a['closure']),
        }
        collisions = {code:sorted(locs) for code,locs in collisions.items() if locs}
        if collisions:
            pairs.append({'activity_ids':[aid,bid], 'collisions':collisions,
                'shareable':bool(common_occupied) and legal_mix(kinds),
                'common_occupied':sorted(common_occupied)})
    for aid,a in activities.items():
        minimum_accesses=(2*a['total_accesses']+2)//3 if scenario in ('B','C') else a['total_accesses']
        if a['planned_start_week']+minimum_accesses-1 > horizon:
            diagnostics.append({'code':'workload','activity_ids':[aid],'message':'Required weekly accesses do not fit after planned start.'})
        for loc in sorted(footprints[aid]['occupied']):
            if scenario=='A' and supply[loc] == 0: diagnostics.append({'code':'capacity','activity_ids':[aid],'location_ids':[loc],'message':'Required location has zero supply.'})
    for contract in sorted({p['contract_number'] for p in projects.values()}):
        records=[p for p in projects.values() if p['contract_number']==contract]
        if len({(p['contract_priority'],p['planned_completion_date']) for p in records}) != 1:
            diagnostics.append({'code':'results_consistency','contract_ids':[contract],'message':'Contract types disagree on target or priority.'})
        if not any(a['contract_number']==contract for a in activities.values()):
            diagnostics.append({'code':'results_consistency','contract_ids':[contract],'message':'Contract has no activities from which to derive completion.'})
    if sum(a['total_accesses']*len(footprints[aid]['occupied']) for aid,a in activities.items()) > 20000:
        return {'limit':True,'diagnostics':[{'code':'submission_limit','message':'Canonical occupancy exceeds validator 20,000-row limit.'}]}
    if len(pairs)*horizon>300000:
        return {'limit':True,'diagnostics':[{'code':'model_limit','message':'Model exceeds 300,000 weekly possession-conflict constraints.'}]}
    return dict(activities=activities,projects=projects,horizon=horizon,footprints=footprints,supply=supply,pairs=pairs,diagnostics=diagnostics,limit=False)
