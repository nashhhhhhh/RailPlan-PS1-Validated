"""Pure orchestration. Exact source fingerprints differ when CSV bytes differ."""
import json
from .contracts import VERSION, ValidationReport, snapshot
from .submission import fingerprint, parse_submission
from .rules import evaluate
from .scoring import score

def validate(dataset, files, scenario, physical_nights: dict[tuple[str, int], int] | None = None):
    tables, errors = parse_submission(files,scenario)
    state = evaluate(dataset,tables,scenario,physical_nights=physical_nights)
    components, result_errors = score(dataset,state,tables['RESULTS.csv'],scenario)
    errors += state['violations'] + result_errors
    for item in errors:
        item['contract_ids']=sorted(set(item['contract_ids']) | {
            state['activities'][aid]['contract_number'] for aid in item['activity_ids'] if aid in state['activities']})
    errors.sort(key=lambda r:(r['rule_code'],r['week'] or 0,r['activity_ids'],r['contract_ids'],r['location_ids'],json.dumps(r,sort_keys=True)))
    warnings=sorted(state['warnings'],key=lambda r:json.dumps(r,sort_keys=True))
    policy=snapshot()
    workload=state['workload']
    source_identity = {'scenario':scenario,'files':files}
    if physical_nights is not None:
        source_identity['physical_nights'] = state['physical_night_identity']
    return ValidationReport(scenario=scenario,feasible=not errors,
        validation_context='submission' if physical_nights is None else 'rich_schedule',
        physical_validation_complete=state['physical_validation_complete'],
        validation_status='invalid_submission' if any(v['rule_code']=='schema' for v in errors) else ('infeasible' if errors else 'feasible'),
        validator_version=VERSION,dataset_fingerprint=dataset['fingerprint'],
        submission_fingerprint=fingerprint(source_identity),rule_policy=policy,
        hard_violations=errors,warnings=warnings,objective_components=components,
        objective_score=None if errors else components['diagnostic_objective'],
        completeness={'activity_count':len(workload),'activities_present':sum(w['present'] for w in workload),
            'activities_complete':sum(w['complete'] for w in workload),'workload_gate_passed':all(w['complete'] for w in workload),
            'activities':workload},capacity_hotspots=state['capacity_hotspots'],
        active_rule_assumptions=[v for k,v in sorted(policy.items()) if isinstance(v,str) and k!='version']).model_dump()
