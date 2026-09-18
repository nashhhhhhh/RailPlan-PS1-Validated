"""Short-transaction persistence of trusted pure-service outcomes; no solving here."""
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from uuid import uuid4
import ortools
from fastapi import HTTPException
from sqlalchemy import text
from app import repository
from app.ps1_validation.contracts import VERSION as VALIDATOR_VERSION, POLICY, snapshot
from app.ps1_validation.submission import fingerprint
from .contracts import OptimiseInput, ScenarioBOptimiseInput, ScenarioCOptimiseInput, Placement, VERSION
from .saved_contracts import SavedOptimiseResult
from .exporter import export_bundle
from .preprocessing import prepare, InputError

OBJECTIVE_POLICIES={'A':'ps1-objective/scenario-a-scale10-lex5/1','B':'ps1-objective/scenario-b-official-lex7/1','C':'ps1-objective/scenario-c-scale10-lex9/1'}
OBJECTIVE_POLICY=OBJECTIVE_POLICIES['A']
OUTCOMES={s:('bounded' if s=='UNKNOWN' else s.lower()) for s in
          ('OPTIMAL','FEASIBLE','INFEASIBLE','UNKNOWN','MODEL_LIMIT','VALIDATION_FAILED','ERROR','MODEL_INVALID')}

def get_run(db,actor,run_id,instance_id=None):
    row=db.execute(text('''SELECT * FROM railplan.ps1_optimisation_runs
        WHERE id=:id AND operator_id=:op AND (CAST(:instance AS uuid) IS NULL OR instance_id=:instance)'''),
        {'id':run_id,'op':actor['operator_id'],'instance':instance_id}).mappings().one_or_none()
    if row is None:raise HTTPException(404,'PS1 optimisation not found')
    return dict(row)

def resolve(db,actor,instance,payload,scenario='A'):
    option_type={'A':OptimiseInput,'B':ScenarioBOptimiseInput,'C':ScenarioCOptimiseInput}[scenario]
    options=option_type.model_validate({k:getattr(payload,k) for k in option_type.model_fields})
    if payload.baseline_run_id:
        baseline=get_run(db,actor,payload.baseline_run_id,instance['id'])
        if not baseline['publishable']:raise HTTPException(422,'Baseline run must have an internally accepted schedule')
        baseline_scenario=baseline.get('scenario','A') # Pre-0008/test rows are Scenario A.
        if scenario=='A' and baseline_scenario!='A':raise HTTPException(422,'Scenario A requires a Scenario A baseline')
        if scenario=='B' and baseline_scenario not in ('A','B'):raise HTTPException(422,'Baseline scenario is incompatible with Scenario B')
        if scenario=='C' and baseline_scenario not in ('A','B','C'):raise HTTPException(422,'Baseline scenario is incompatible with Scenario C')
        rows=db.execute(text('''SELECT activity_id,access_seq,week,physical_night,access_night,eclo
          FROM railplan.ps1_optimisation_accesses WHERE run_id=:id AND operator_id=:op AND instance_id=:instance
          ORDER BY activity_id,access_seq'''),{'id':baseline['id'],'op':actor['operator_id'],'instance':instance['id']}).mappings()
        options.baseline_placements=[Placement.model_validate(dict(row)) for row in rows]
    # Validate placement references even if the dataset would hit a solver model limit.
    activities={a['activity_id']:a for a in instance['dataset']['tables']['activity_details']}
    projects={(p['contract_number'],p['activity_type']):p for p in instance['dataset']['tables']['project_details']}
    for name in ('locked_placements','baseline_placements'):
        seen=set()
        for p in getattr(options,name):
            key=p.activity_id,p.access_seq; a=activities.get(p.activity_id)
            if key in seen or a is None or p.access_seq>a['total_accesses']:
                raise InputError(f'{name}: duplicate or unknown activity/access_seq {key}')
            seen.add(key)
            cap=projects[a['contract_number'],a['activity_type']]['number_of_maximum_access_per_week']
            if p.week>instance['dataset']['parameters']['horizon_weeks'] or p.physical_night>options.physical_nights_per_week or (p.access_night is not None and p.access_night>cap):
                raise InputError(f'{name}: placement outside week/night/allocation bounds {key}')
    return options

def effective_configuration(instance,options,baseline_run_id=None,scenario='A'):
    config=options.model_dump(mode='json')
    for key in ('locked_placements','baseline_placements'):
        config[key]=sorted(config[key],key=lambda p:(p['activity_id'],p['access_seq']))
    stage_order={'A':['weighted_overrun_scaled_10','raw_contract_overrun_days','completion_weeks','baseline_movements','stable_placement_rank'],
        'B':['official_scenario_b_objective','excess_access_nights_total','eclo_nights_total','workload_over_delivery_scaled','completion_weeks','baseline_movements','stable_placement_rank'],
        'C':['official_scenario_c_objective_scaled_10','priority_weighted_overrun_scaled_10','excess_access_nights_total','eclo_nights_total','raw_contract_overrun_days','workload_over_delivery_scaled','completion_weeks','baseline_movements','stable_placement_rank']}[scenario]
    return {'instance_id':str(instance['id']),'dataset_fingerprint':instance['dataset']['fingerprint'],'scenario':scenario,
        'optimiser_version':VERSION,'validator_version':VALIDATOR_VERSION,'policy_version':POLICY.version,
        'policy_snapshot':snapshot(),'objective_policy':OBJECTIVE_POLICY if scenario=='A' else OBJECTIVE_POLICIES[scenario],'ortools_version':ortools.__version__,
        'fixed_settings':{'num_search_workers':1,'night_domain':'configured_uniform_1_to_7_per_week',
            'allocation_alignment':'one_local_index_per_used_physical_night','possession_assignment':'one_group_per_location_week_physical_night',
            'stage_order':stage_order},
        'solver_options':config,'baseline_run_id':str(baseline_run_id) if baseline_run_id else None}

def existing_key(db,actor,instance_id,key,digest,lock=False):
    if key is None:return None
    params={'op':actor['operator_id'],'instance':instance_id,'key':key}
    if lock:
        db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:scope,0))'),
            {'scope':f'ps1-opt-key/{actor["operator_id"]}/{instance_id}/{key}'})
    row=db.execute(text('''SELECT input_fingerprint,run_id FROM railplan.ps1_optimisation_keys
        WHERE operator_id=:op AND instance_id=:instance AND idempotency_key=:key'''),params).mappings().one_or_none()
    if row is None:return None
    if row['input_fingerprint']!=digest:raise HTTPException(409,'Idempotency key already used for different optimiser input')
    return get_run(db,actor,row['run_id'],instance_id)

def response(run,created):
    return SavedOptimiseResult.model_validate({**run['result_snapshot'],'run_id':run['id'],'created':created,'reused':not created,
        'created_at':run['created_at'],'terminal_outcome':run['terminal_outcome'],'input_fingerprint':run['input_fingerprint']})

def accepted(result):
    report=result.validation_report
    return bool(result.publishable and result.solver_status in ('FEASIBLE','OPTIMAL') and report is not None
        and report.feasible and report.physical_validation_complete and not report.hard_violations
        and result.physical_validation_complete and result.submission_files and report.objective_score is not None)

def primary_metrics(result,is_accepted):
    score=Decimal(result.validation_report.objective_score) if is_accepted else None
    bound=gap=None
    primary_name={'A':'weighted_overrun_scaled_10','B':'official_scenario_b_objective','C':'official_scenario_c_objective_scaled_10'}[result.scenario]
    stages=[s for s in result.stages if s.get('name')==primary_name]
    if len(stages)==1 and stages[0].get('status') in ('OPTIMAL','FEASIBLE'):
        try:
            value=Decimal(str(stages[0]['best_bound']))/(Decimal(10) if result.scenario in ('A','C') else Decimal(1))
            if value.is_finite() and value>=0 and (score is None or value<=score):bound=value
        except (KeyError,InvalidOperation,ValueError):pass
    if score is not None and bound is not None:
        gap=((score-bound)/max(abs(score),Decimal(1))).quantize(Decimal('0.000000000001'),rounding=ROUND_HALF_UP)
    return score,bound,gap

def schedule_records(instance,options,result,scenario=None):
    if not accepted(result):return {'accesses':[],'occupancies':[],'contract_results':[]}
    scenario=scenario or result.scenario
    data=prepare(instance['dataset'],options,scenario)
    bundle=export_bundle(instance['dataset'],data,result.physical_nights,scenario)
    if bundle.files!=result.submission_files:raise RuntimeError('Trusted service CSVs do not match canonical export')
    locks={(p.activity_id,p.access_seq) for p in options.locked_placements}
    baseline={(p.activity_id,p.access_seq):p for p in options.baseline_placements}
    records=[]
    for row in bundle.accesses:
        key=row['activity_id'],row['access_seq']; old=baseline.get(key)
        records.append({**row,'physical_night':bundle.physical_nights[row['activity_id'],row['week']],
            'locked':key in locks,'baseline_week':old.week if old else None,'baseline_physical_night':old.physical_night if old else None})
    # Weighted score is already retained exactly per activity in the rich snapshot.
    # Optional per-contract aggregation is intentionally null, never confused with raw days.
    contracts=[{k:v for k,v in row.items() if k!='scenario'}|{'weighted_overrun':None} for row in bundle.contract_results]
    return {'accesses':records,'occupancies':bundle.occupancies,'contract_results':contracts}

def persist(db,actor,instance,payload,configuration,digest,result,records,started,completed,scenario=None):
    """Caller owns final transaction; errors MUST propagate, including commit failure."""
    existing=existing_key(db,actor,instance['id'],payload.idempotency_key,digest,lock=True)
    if existing:return response(existing,False)
    is_accepted=accepted(result)
    if result.publishable!=is_accepted:raise RuntimeError('Inconsistent trusted optimisation acceptance flag')
    score,bound,gap=primary_metrics(result,is_accepted)
    run_id=uuid4()
    report=result.validation_report.model_dump(mode='json') if result.validation_report else None
    scenario=scenario or result.scenario
    params={'id':run_id,'instance':instance['id'],'op':actor['operator_id'],'creator':actor['id'],'baseline':payload.baseline_run_id,'scenario':scenario,
        'status':result.solver_status,'outcome':OUTCOMES[result.solver_status],
        'optimiser':VERSION,'validator':VALIDATOR_VERSION,'policy':POLICY.version,'dataset':instance['dataset']['fingerprint'],'fingerprint':digest,
        'request':json.dumps(payload.model_dump(mode='json',exclude_unset=True)),'configuration':json.dumps(configuration),
        'result':result.model_dump_json(),'validation':json.dumps(report) if report else None,'diagnostics':json.dumps(result.diagnostics),
        'primary':result.primary_optimal,'lex':result.lexicographic_complete,'physical':result.physical_validation_complete,'accepted':is_accepted,
        'score':score,'bound':bound,'gap':gap,'duration':result.solve_time_seconds,'started':started,'completed':completed,
        'csvs':json.dumps(result.submission_files) if is_accepted else None,'schedule':json.dumps(records)}
    db.execute(text('''INSERT INTO railplan.ps1_optimisation_runs
      (id,instance_id,operator_id,created_by,baseline_run_id,scenario,solver_status,terminal_outcome,
       optimiser_version,validator_version,policy_version,dataset_fingerprint,input_fingerprint,request_snapshot,solver_configuration,
       result_snapshot,validation_snapshot,diagnostics,primary_optimal,lexicographic_complete,physical_validation_complete,publishable,
       objective_score,primary_objective_bound,primary_objective_gap,solve_duration_seconds,started_at,completed_at,accepted_csvs,schedule_snapshot)
      VALUES(:id,:instance,:op,:creator,:baseline,:scenario,:status,:outcome,:optimiser,:validator,:policy,:dataset,:fingerprint,
       CAST(:request AS jsonb),CAST(:configuration AS jsonb),CAST(:result AS jsonb),CAST(:validation AS jsonb),CAST(:diagnostics AS jsonb),
       :primary,:lex,:physical,:accepted,:score,:bound,:gap,:duration,:started,:completed,CAST(:csvs AS jsonb),CAST(:schedule AS jsonb))'''),params)
    # Fixed developer-authored identifiers only. Values are always parameters.
    columns={'accesses':'activity_id,access_seq,week,physical_night,access_night,eclo,locked,baseline_week,baseline_physical_night',
        'occupancies':'activity_id,week,location_id,co_share_group',
        'contract_results':'contract_number,simulated_completion_date,overrun_days,weighted_overrun'}
    for name,fields in columns.items():
        if records[name]:
            values=','.join(':'+f for f in fields.split(','))
            db.execute(text(f'INSERT INTO railplan.ps1_optimisation_{name} (run_id,instance_id,operator_id,{fields}) VALUES(:run_id,:instance_id,:operator_id,{values})'),
                [{**row,'run_id':run_id,'instance_id':instance['id'],'operator_id':actor['operator_id']} for row in records[name]])
    if payload.idempotency_key is not None:
        db.execute(text('''INSERT INTO railplan.ps1_optimisation_keys(operator_id,instance_id,idempotency_key,input_fingerprint,run_id)
            VALUES(:op,:instance,:key,:fingerprint,:id)'''),{**params,'key':payload.idempotency_key})
    repository.event(db,actor,'ps1_optimisation_completed','ps1_optimisation',run_id,f'Internal Scenario {scenario} terminal result: {result.solver_status}')
    return response(get_run(db,actor,run_id,instance['id']),True)
