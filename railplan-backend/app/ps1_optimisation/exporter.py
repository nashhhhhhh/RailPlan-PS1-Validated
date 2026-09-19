"""Export organiser schemas without conflating any of the three night identities."""
import csv
import io
from collections import defaultdict
from datetime import date, timedelta
from dataclasses import dataclass
from app.ps1_validation.contracts import HEADERS

@dataclass(frozen=True)
class ExportBundle:
    accesses: list[dict]
    occupancies: list[dict]
    contract_results: list[dict]
    files: dict[str,str]
    physical_nights: dict[tuple[str,int],int]

def export_bundle(dataset, data, placements, scenario='A'):
    rows={name:[] for name in HEADERS}
    location_nights=defaultdict(set)
    for r in placements:
        for loc in data['footprints'][r.activity_id]['occupied']:
            location_nights[loc,r.week].add(r.physical_night)
    groups={(loc,w,n):f'g{i:03d}' for (loc,w),ns in sorted(location_nights.items()) for i,n in enumerate(sorted(ns),1)}
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
