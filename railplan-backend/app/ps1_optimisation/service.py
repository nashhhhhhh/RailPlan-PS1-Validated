"""Orchestration with a fail-closed rich-validation publication gate."""
from datetime import date, timedelta
import ortools
from app.ps1_validation.service import validate
from app.ps1_validation.contracts import snapshot, ValidationReport
from .contracts import OptimiseInput, OptimiseResult
from .preprocessing import prepare
from .scenario_a import solve
from .exporter import export

def optimise(dataset, options: OptimiseInput | None = None):
    options=options or OptimiseInput()
    settings={**options.model_dump(), 'ortools_version':ortools.__version__,'workers':1,'policy':snapshot(),
              'physical_night_policy':'Configured 1..7 network-wide night slots per calendar week, same domain every week; no actual dated engineering-night calendar supplied.',
              'local_night_policy':'One distinct local index per used physical night within contract/type/week.',
              'possession_policy':'All activities at one location/week/physical night form one legal possession; labels are local.'}
    data=prepare(dataset,options)
    result=OptimiseResult(solver_status='UNKNOWN',solve_time_seconds=0,settings=settings)
    if data['limit'] or data['diagnostics']:
        result.solver_status='MODEL_LIMIT' if data['limit'] else 'INFEASIBLE'
        result.diagnostics=data['diagnostics']; return result
    solved=solve(dataset,data,options)
    result.solver_status=solved['status']; result.solve_time_seconds=solved['solve_time_seconds']
    result.primary_optimal=solved['primary_optimal']; result.lexicographic_complete=solved['lexicographic_complete']
    result.stages=solved['stages']; result.diagnostics=solved['diagnostics']
    result.settings['model_build_seconds']=solved['build_seconds']
    if solved['placements'] is None: return result
    files,mapping=export(dataset,data,solved['placements'])
    report=validate(dataset,files,'A',physical_nights=mapping)
    result.validation_report=ValidationReport.model_validate(report)
    result.objective_components=report['objective_components']
    result.physical_validation_complete=report['physical_validation_complete']
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
        old=(start+timedelta(weeks=max(r.week for r in records),days=-1)).isoformat() if len(records)==a['total_accesses'] else None
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
