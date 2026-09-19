"""Independently audit exported PS1 CSV possession closures.

This deliberately does not call the RailPlan validator or optimiser.  It reads
the final CSV grouping decisions, rebuilds canonical footprints from organiser
input, and reports directional cross-group closure intrusions.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import io
import json
from pathlib import Path

from app.ps1 import load_files, parse_instance
from app.ps1_validation.network import chains, expand


def _legal_mix(types: list[str]) -> bool:
    counts=Counter(types)
    return bool(types) and ((counts['PM']==1 and len(types)==1) or
        (counts['PM']==0 and counts['PC']<=1 and counts['C']<=4-counts['PC']))


def audit_files(dataset: dict, files: dict[str,str]) -> dict:
    activities={row['activity_id']:row for row in dataset['tables']['activity_details']}
    projects={(row['contract_number'],row['activity_type']):row for row in dataset['tables']['project_details']}
    network=chains(dataset)
    footprints={aid:expand(activity,projects[activity['contract_number'],activity['activity_type']],network)
        for aid,activity in activities.items()}
    access=list(csv.DictReader(io.StringIO(files['SCHEDULE_ACCESS.csv'])))
    occupancy=list(csv.DictReader(io.StringIO(files['SCHEDULE_OCCUPANCY.csv'])))
    scheduled=defaultdict(set)
    for row in access:
        scheduled[int(row['week'])].add(row['activity_id'])
    assignment={}
    groups=defaultdict(set)
    for row in occupancy:
        key=row['activity_id'],int(row['week']),row['location_id']
        if key in assignment:
            raise ValueError(f'Duplicate occupancy row: {key}')
        assignment[key]=row['co_share_group']
        groups[row['location_id'],int(row['week']),row['co_share_group']].add(row['activity_id'])
    legal={key:_legal_mix([
        projects[activities[aid]['contract_number'],activities[aid]['activity_type']]['access_type']
        for aid in sorted(ids)]) for key,ids in groups.items()}
    findings=[]
    for week,ids in sorted(scheduled.items()):
        for owner in sorted(ids):
            for offender in sorted(ids-{owner}):
                common=footprints[owner]['occupied'] & footprints[offender]['occupied']
                shared=bool(common) and all(
                    (owner,week,loc) in assignment and (offender,week,loc) in assignment
                    and assignment[owner,week,loc]==assignment[offender,week,loc]
                    and legal.get((loc,week,assignment[owner,week,loc]),False)
                    for loc in common)
                if shared:
                    continue
                locations=sorted(footprints[offender]['occupied'] & footprints[owner]['closure'])
                if locations:
                    findings.append({'week':week,'closure_owner_activity':owner,
                        'offending_activity':offender,'location_ids':locations,
                        'common_location_groups':[
                            {'location_id':loc,'owner_group':assignment.get((owner,week,loc)),
                             'offender_group':assignment.get((offender,week,loc))}
                            for loc in sorted(common)]})
    return {'passed':not findings,'cross_group_closure_violation_count':len(findings),'findings':findings}


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate-dir',type=Path,required=True)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    dataset=parse_instance(load_files())
    results={}
    for scenario in 'ABC':
        directory=args.candidate_dir/f'scenario-{scenario.lower()}'
        if not directory.is_dir():
            results[scenario]={'passed':False,'error':'candidate directory absent'}
            continue
        files={name:(directory/name).read_text(encoding='utf-8') for name in
            ('SCHEDULE_ACCESS.csv','SCHEDULE_OCCUPANCY.csv','RESULTS.csv')}
        results[scenario]=audit_files(dataset,files)
    report={'dataset_fingerprint':dataset['fingerprint'],'scenario_results':results}
    rendered=json.dumps(report,indent=2,sort_keys=True)+'\n'
    if args.output:
        if args.output.exists():
            parser.error('output already exists')
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(rendered,encoding='utf-8',newline='')
    print(rendered,end='')
    return 0 if all(item.get('passed') for item in results.values()) else 1


if __name__=='__main__':
    raise SystemExit(main())
