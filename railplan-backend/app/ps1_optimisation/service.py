"""Orchestration with a fail-closed rich-validation publication gate."""
from datetime import date, timedelta
from decimal import Decimal
import ortools
from app.ps1_validation.service import validate
from app.ps1_validation.contracts import snapshot, ValidationReport
from .contracts import OptimiseInput, ScenarioBOptimiseInput, OptimiseResult
from .preprocessing import prepare
from .scenario_a import solve as solve_a
from .scenario_b import solve as solve_b
from .exporter import export

PHYSICAL_NIGHT_POLICY='Configured 1..7 network-wide night slots per calendar week, same domain every week; no actual dated engineering-night calendar supplied.'

def _optimise(dataset, options, scenario):
    options=options or OptimiseInput()
    settings={**options.model_dump(), 'ortools_version':ortools.__version__,'workers':1,'policy':snapshot(),
              'physical_night_policy':PHYSICAL_NIGHT_POLICY,
              'local_night_policy':'One distinct local index per used physical night within contract/type/week.',
              'possession_policy':'All activities at one location/week/physical night form one legal possession; labels are local.',
              'scenario_b_workload_policy':'Integer scale 2: normal=2, ECLO=3, required=2*total_accesses; over-delivery is allowed and lexicographically minimised.' if scenario=='B' else None}
    data=prepare(dataset,options,scenario)
    result=OptimiseResult(scenario=scenario,solver_status='UNKNOWN',solve_time_seconds=0,settings=settings)
    if data['limit'] or data['diagnostics']:
        result.solver_status='MODEL_LIMIT' if data['limit'] else 'INFEASIBLE'
        result.diagnostics=data['diagnostics']; return result
    solved=(solve_b if scenario=='B' else solve_a)(dataset,data,options)
    result.solver_status=solved['status']; result.solve_time_seconds=solved['solve_time_seconds']
    result.primary_optimal=solved['primary_optimal']; result.lexicographic_complete=solved['lexicographic_complete']
    result.stages=solved['stages']; result.diagnostics=solved['diagnostics']
    result.settings['model_build_seconds']=solved['build_seconds']
    result.baseline_movement=solved.get('baseline_movement',0)
    if solved['placements'] is None: return result
    files,mapping=export(dataset,data,solved['placements'],scenario)
    report=validate(dataset,files,scenario,physical_nights=mapping)
    result.validation_report=ValidationReport.model_validate(report)
    result.objective_components=report['objective_components']
    result.workload_delivery=report['completeness']['activities']
    result.capacity_hotspots=_hotspots(report,dataset,mapping)
    result.contract_completion_gate=scenario=='B' and all((r['overrun_days'] or 0)==0 for r in report['objective_components']['contract_results'])
    result.physical_validation_complete=report['physical_validation_complete']
    if scenario=='B' and report['objective_score'] is not None:
        components=report['objective_components']
        expected=Decimal(7*components['excess_access_nights_total']+5*components['eclo_nights_total']).quantize(Decimal('0.01'))
        if Decimal(report['objective_score']) != expected:
            report['hard_violations'].append({'rule_code':'results_consistency','message':'Scenario B objective does not equal 7 * excess access nights + 5 * ECLO nights.','week':None,'activity_ids':[],'contract_ids':[],'location_ids':[],'possession_group':None,'evidence':{'expected':str(expected),'reported':report['objective_score']}})
            report['feasible']=False
            report['validation_status']='infeasible'
            result.validation_report=ValidationReport.model_validate(report)
    if not (report['feasible'] and report['physical_validation_complete'] and not report['hard_violations']):
        result.solver_status='VALIDATION_FAILED'
        result.diagnostics.append({'code':'rich_validation_rejected','hard_violations':report['hard_violations']})
        result.failed_candidate={'submission_files':files,'physical_nights':[p.model_dump() for p in solved['placements']], 'diagnostic_only':True}
        return result
    result.publishable=True; result.submission_files=files; result.physical_nights=solved['placements']
    baseline={}
    for placement in options.baseline_placements: baseline.setdefault(placement.activity_id,[]).append(placement)
    start=date.fromisoformat(dataset['parameters']['horizon_start'])
    for component in report['objective_components']['activity_components']:
        aid=component['activity_id']; a=data['activities'][aid]; p=data['projects'][a['contract_number'],a['activity_type']]
        records=baseline.get(aid,[])
        old=(start+timedelta(weeks=max(r.week for r in records),days=-1)).isoformat() if records else None
        result.completion_changes.append({'kind':'activity',**component,'planned_completion_date':p['planned_completion_date'],
            'baseline_completion_date':old,'change_days':(date.fromisoformat(component['completion_date'])-date.fromisoformat(old)).days if old else None,
            'reason':'Derived from final scheduled access; constrained by workload, starts, dependencies, physical safety, supply and allocations. No causal sensitivity analysis performed.'})
    for component in report['objective_components']['contract_results']:
        contract=component['contract_number']; members=[a for a in result.completion_changes if a.get('contract_number')==contract and a['kind']=='activity']
        old=max(a['baseline_completion_date'] for a in members) if members and all(a['baseline_completion_date'] for a in members) else None
        result.completion_changes.append({'kind':'contract',**component,'baseline_completion_date':old,
            'change_days':(date.fromisoformat(component['simulated_completion_date'])-date.fromisoformat(old)).days if old else None,
            'reason':'Latest activity completion in the contract.'})
    return result

def _hotspots(report,dataset,mapping):
    activities={a['activity_id']:a for a in dataset['tables']['activity_details']}
    enriched=[]
    for row in report['capacity_hotspots']:
        ids=sorted({aid for group in row['possession_groups'] for aid in group['activity_ids']})
        enriched.append({**row,'available_supply':row['supply'],'used_possession_groups':row['used'],
            'activity_ids':ids,'contract_ids':sorted({activities[aid]['contract_number'] for aid in ids}),
            'co_share_groups':[g['co_share_group'] for g in row['possession_groups']],
            'physical_night_assignments':sorted([{'activity_id':aid,'physical_night':mapping.get((aid,row['week']))} for aid in ids],key=lambda x:x['activity_id'])})
    return enriched

def optimise(dataset, options: OptimiseInput | None = None):
    return _optimise(dataset,options or OptimiseInput(),'A')

def optimise_scenario_b(dataset, options: ScenarioBOptimiseInput | None = None):
    return _optimise(dataset,options or ScenarioBOptimiseInput(),'B')
