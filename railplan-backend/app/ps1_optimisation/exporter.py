"""Export organiser schemas without conflating any of the three night identities."""
import csv
import io
from collections import defaultdict
from datetime import date, timedelta
from dataclasses import dataclass
from app.ps1_validation.contracts import HEADERS
from app.ps1_validation.rules import legal_mix

@dataclass(frozen=True)
class ExportBundle:
    accesses: list[dict]
    occupancies: list[dict]
    contract_results: list[dict]
    files: dict[str,str]
    physical_nights: dict[tuple[str,int],int]

def possession_groups(data, placements):
    """Derive exported groups from the model's explicit possession slot.

    Physical night is the solver's possession identity within a location/week.
    Refuse inconsistent caller-supplied placements rather than serialising a
    grouping that changes the schedule's closure semantics.
    """
    by_activity_week={}
    members=defaultdict(set)
    for row in placements:
        key=row.activity_id,row.week
        if key in by_activity_week and by_activity_week[key]!=row.physical_night:
            raise ValueError(f'Multiple physical possession slots for {key}')
        by_activity_week[key]=row.physical_night
        for loc in data['footprints'][row.activity_id]['occupied']:
            members[loc,row.week,row.physical_night].add(row.activity_id)
    for pair in data['pairs']:
        aid,bid=pair['activity_ids']
        common_weeks={week for activity,week in by_activity_week if activity==aid} & {
            week for activity,week in by_activity_week if activity==bid}
        for week in common_weeks:
            same=by_activity_week[aid,week]==by_activity_week[bid,week]
            if not pair['shareable'] or not same:
                raise ValueError(f'Invalid possession relationship for {aid}/{bid} in week {week}')
    for (loc,week,night),ids in members.items():
        kinds=[data['projects'][data['activities'][aid]['contract_number'],data['activities'][aid]['activity_type']]['access_type']
            for aid in sorted(ids)]
        if not legal_mix(kinds):
            raise ValueError(f'Illegal possession mix at {loc}, week {week}, physical night {night}')
    location_nights=defaultdict(set)
    for loc,week,night in members:
        location_nights[loc,week].add(night)
    return {(loc,week,night):f'g{i:03d}'
        for (loc,week),nights in sorted(location_nights.items())
        for i,night in enumerate(sorted(nights),1)}

def export_bundle(dataset, data, placements, scenario='A'):
    rows={name:[] for name in HEADERS}
    groups=possession_groups(data,placements)
    ends={}; mapping={}
    for r in sorted(placements,key=lambda r:(r.activity_id,r.access_seq)):
        rows['SCHEDULE_ACCESS.csv'].append(dict(activity_id=r.activity_id,access_seq=r.access_seq,week=r.week,eclo=r.eclo or 0,access_night=r.access_night))
        mapping[r.activity_id,r.week]=r.physical_night
        contract=data['activities'][r.activity_id]['contract_number']
        ends[contract]=max(ends.get(contract,0),r.week)
        for loc in sorted(data['footprints'][r.activity_id]['occupied']):
            rows['SCHEDULE_OCCUPANCY.csv'].append(dict(activity_id=r.activity_id,week=r.week,location_id=loc,co_share_group=groups[loc,r.week,r.physical_night]))
    start=date.fromisoformat(dataset['parameters']['horizon_start'])
    for contract,week in sorted(ends.items()):
        p=next(p for p in data['projects'].values() if p['contract_number']==contract)
        complete=start+timedelta(weeks=week,days=-1)
        rows['RESULTS.csv'].append(dict(scenario=scenario,contract_number=contract,simulated_completion_date=complete.isoformat(),overrun_days=max(0,(complete-date.fromisoformat(p['planned_completion_date'])).days)))
    files={}
    for name,header in HEADERS.items():
        stream=io.StringIO(); writer=csv.DictWriter(stream,fieldnames=header.split(','),lineterminator='\n')
        writer.writeheader(); writer.writerows(rows[name]); files[name]=stream.getvalue()
    return ExportBundle(rows['SCHEDULE_ACCESS.csv'],rows['SCHEDULE_OCCUPANCY.csv'],rows['RESULTS.csv'],files,mapping)

def export(dataset, data, placements, scenario='A'):
    """Compatibility wrapper for the pure optimiser and offline callers."""
    bundle=export_bundle(dataset,data,placements,scenario)
    return bundle.files,bundle.physical_nights
