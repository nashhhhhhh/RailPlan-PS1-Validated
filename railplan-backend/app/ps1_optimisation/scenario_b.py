"""Shared elastic CP-SAT core for Scenario B (fixed dates) and C (balanced)."""
from collections import defaultdict
from datetime import date
from time import monotonic
from ortools.sat.python import cp_model
from .contracts import Placement


def solve(dataset, data, options, scenario='B'):
    if scenario not in ('B','C'):raise ValueError('Elastic model supports Scenario B or C')
    built_at=monotonic(); model=cp_model.CpModel()
    activities,projects=data['activities'],data['projects']
    horizon,nights=data['horizon'],options.physical_nights_per_week
    weeks=range(1,horizon+1); night_ids=range(1,nights+1)
    guards={}
    def guard(code):
        if code not in guards:
            guards[code]=model.NewBoolVar('rule:'+code);model.AddAssumption(guards[code])
        return guards[code]
    def enforce(expression,code):
        return model.Add(expression).OnlyEnforceIf(guard(code))

    active,W,N,L,E,z,x,present,physical_week,local,completion,start_week={},{},{},{},{},{},{},{},{},{},{},{}
    by_project=defaultdict(list);by_location=defaultdict(list)
    required_scaled={};delivered_scaled={};over_delivery={}
    for aid,a in activities.items():
        project=projects[a['contract_number'],a['activity_type']]
        cap=project['number_of_maximum_access_per_week']
        by_project[a['contract_number'],a['activity_type']].append(aid)
        for loc in sorted(data['footprints'][aid]['occupied']):by_location[loc].append(aid)
        for w in weeks:
            present[aid,w]=model.NewBoolVar(f'present:{aid}:{w}')
            physical_week[aid,w]=model.NewIntVar(0,nights,f'physical_week:{aid}:{w}')
            local[aid,w]=model.NewIntVar(0,cap,f'local:{aid}:{w}')
            for n in night_ids:x[aid,w,n]=model.NewBoolVar(f'x:{aid}:{w}:{n}')
            model.Add(sum(x[aid,w,n] for n in night_ids)==present[aid,w])
            model.Add(physical_week[aid,w]==sum(n*x[aid,w,n] for n in night_ids))
            if w<a['planned_start_week']:enforce(present[aid,w]==0,'planned_start')
        maximum=a['total_accesses']
        for k in range(1,maximum+1):
            key=aid,k
            active[key]=model.NewBoolVar(f'active:{aid}:{k}')
            W[key]=model.NewIntVar(0,horizon,f'week:{aid}:{k}')
            N[key]=model.NewIntVar(0,nights,f'physical:{aid}:{k}')
            L[key]=model.NewIntVar(0,cap,f'access_night:{aid}:{k}')
            E[key]=model.NewBoolVar(f'eclo:{aid}:{k}')
            choices=[]
            for w in weeks:
                for n in night_ids:
                    value=model.NewBoolVar(f'z:{aid}:{k}:{w}:{n}')
                    z[aid,k,w,n]=value;choices.append(value)
            model.Add(sum(choices)==active[key])
            model.Add(W[key]==sum(w*z[aid,k,w,n] for w in weeks for n in night_ids))
            model.Add(N[key]==sum(n*z[aid,k,w,n] for w in weeks for n in night_ids))
            model.AddElement(W[key],[0]+[local[aid,w] for w in weeks],L[key])
            model.Add(E[key]<=active[key])
            if k==1:enforce(active[key]==1,'workload')
            else:
                model.Add(active[key]<=active[aid,k-1])
                model.Add(W[key]>W[aid,k-1]).OnlyEnforceIf(active[key],guard('access_sequence'))
        for w in weeks:
            for n in night_ids:model.Add(x[aid,w,n]==sum(z[aid,k,w,n] for k in range(1,maximum+1)))
            enforce(sum(z[aid,k,w,n] for k in range(1,maximum+1) for n in night_ids)<=1,'weekly_activity_access')
        required_scaled[aid]=2*a['total_accesses']
        delivered_scaled[aid]=sum(2*active[aid,k]+E[aid,k] for k in range(1,maximum+1))
        enforce(delivered_scaled[aid]>=required_scaled[aid],'workload')
        over_delivery[aid]=model.NewIntVar(0,2*maximum,f'over_delivery:{aid}')
        model.Add(over_delivery[aid]==delivered_scaled[aid]-required_scaled[aid])
        completion[aid]=model.NewIntVar(1,horizon,f'completion:{aid}')
        model.AddMaxEquality(completion[aid],[W[aid,k] for k in range(1,maximum+1)])
        candidates=[]
        for k in range(1,maximum+1):
            candidate=model.NewIntVar(1,horizon+1,f'start_candidate:{aid}:{k}')
            model.Add(candidate==W[aid,k]).OnlyEnforceIf(active[aid,k])
            model.Add(candidate==horizon+1).OnlyEnforceIf(active[aid,k].Not())
            candidates.append(candidate)
        start_week[aid]=model.NewIntVar(1,horizon,f'start:{aid}')
        model.AddMinEquality(start_week[aid],candidates)

    for aid,a in activities.items():
        if a['predecessor_activity_id']:
            enforce(start_week[aid]>completion[a['predecessor_activity_id']],'dependency')

    # Contract-local access-night labels remain independent from physical nights.
    for key,ids in sorted(by_project.items()):
        project=projects[key];cap=project['number_of_maximum_access_per_week']
        for w in weeks:
            used=[];labels=[]
            for n in night_ids:
                u=model.NewBoolVar(f'used:{key}:{w}:{n}')
                model.AddMaxEquality(u,[x[aid,w,n] for aid in ids]);used.append(u)
                label=model.NewIntVarFromDomain(cp_model.Domain.FromValues([-n]+list(range(1,cap+1))),f'label:{key}:{w}:{n}')
                model.Add(label==-n).OnlyEnforceIf(u.Not());model.Add(label>=1).OnlyEnforceIf(u);labels.append(label)
                enforce(sum(x[aid,w,n] for aid in ids)<=project['number_of_workfronts'],'workfront')
            model.AddAllDifferent(labels);enforce(sum(used)<=cap,'weekly_allocation')
            for aid in ids:model.AddElement(physical_week[aid,w],[0]+labels,local[aid,w])

    excess={};slots={}
    for loc,ids in sorted(by_location.items()):
        pm=[aid for aid in ids if projects[activities[aid]['contract_number'],activities[aid]['activity_type']]['access_type']=='PM']
        pc=[aid for aid in ids if projects[activities[aid]['contract_number'],activities[aid]['activity_type']]['access_type']=='PC']
        for w in weeks:
            loc_slots=[]
            for n in night_ids:
                slot=model.NewBoolVar(f'possession:{loc}:{w}:{n}');slots[loc,w,n]=slot
                model.AddMaxEquality(slot,[x[aid,w,n] for aid in ids]);loc_slots.append(slot)
                enforce(sum(x[aid,w,n] for aid in pc)<=1,'possession_mix')
                enforce(sum(x[aid,w,n] for aid in pm)<=1,'possession_mix')
                enforce(sum(x[aid,w,n] for aid in ids)<=4-3*sum(x[aid,w,n] for aid in pm),'possession_mix')
            used=sum(loc_slots);cap=data['supply'][loc]
            excess[loc,w]=model.NewIntVar(0,nights,f'excess:{loc}:{w}')
            model.AddMaxEquality(excess[loc,w],[0,used-cap])

    for pair in data['pairs']:
        aid,bid=pair['activity_ids']
        for w in weeks:
            # Both channel variables are zero when absent.  One conditional
            # inequality is exactly equivalent to seven per-night clauses and
            # substantially reduces Scenario C presolve work.
            model.Add(physical_week[aid,w]!=physical_week[bid,w]).OnlyEnforceIf(
                present[aid,w],present[bid,w],guard('physical_closure'))

    line_windows={}
    if scenario=='C':
        for line in ('ALP','BET'):
            keys=[key for key in sorted(E) if line in data['footprints'][key[0]]['lines']]
            enabled=[E[key] for key in keys]
            line_active=model.NewBoolVar(f'eclo_window_active:{line}')
            if enabled:model.AddMaxEquality(line_active,enabled)
            else:model.Add(line_active==0)
            candidates_min=[];candidates_max=[]
            for key in keys:
                low=model.NewIntVar(1,horizon+1,f'eclo_min_candidate:{line}:{key[0]}:{key[1]}')
                high=model.NewIntVar(0,horizon,f'eclo_max_candidate:{line}:{key[0]}:{key[1]}')
                model.Add(low==W[key]).OnlyEnforceIf(E[key]);model.Add(low==horizon+1).OnlyEnforceIf(E[key].Not())
                model.Add(high==W[key]).OnlyEnforceIf(E[key]);model.Add(high==0).OnlyEnforceIf(E[key].Not())
                candidates_min.append(low);candidates_max.append(high)
            raw_start=model.NewIntVar(1,horizon+1,f'eclo_raw_start:{line}')
            end=model.NewIntVar(0,horizon,f'eclo_end:{line}')
            if candidates_min:
                model.AddMinEquality(raw_start,candidates_min);model.AddMaxEquality(end,candidates_max)
            else:
                model.Add(raw_start==horizon+1);model.Add(end==0)
            start=model.NewIntVar(0,horizon,f'eclo_start:{line}')
            model.Add(start==raw_start).OnlyEnforceIf(line_active);model.Add(start==0).OnlyEnforceIf(line_active.Not())
            enforce(end-start<=1,'eclo_window')
            line_windows[line]={'active':line_active,'start':start,'end':end,'keys':keys}

    for placement in sorted(options.locked_placements,key=lambda r:(r.activity_id,r.access_seq)):
        key=placement.activity_id,placement.access_seq;code=f'lock:{key[0]}:{key[1]}'
        enforce(active[key]==1,code);enforce(W[key]==placement.week,code);enforce(N[key]==placement.physical_night,code)
        if placement.access_night is not None:enforce(L[key]==placement.access_night,code)
        if placement.eclo is not None:enforce(E[key]==placement.eclo,code)

    origin=date.fromisoformat(dataset['parameters']['horizon_start']);contract_completion={};activity_overrun={};contract_overrun={}
    weighted_overrun_scaled=0
    for aid,a in activities.items():
        project=projects[a['contract_number'],a['activity_type']]
        offset=(origin-date.fromisoformat(project['planned_completion_date'])).days-1
        maximum=max(0,7*horizon+offset)
        activity_overrun[aid]=model.NewIntVar(0,maximum,f'activity_overrun:{aid}')
        model.AddMaxEquality(activity_overrun[aid],[0,7*completion[aid]+offset])
        multiplier={1:13,2:12,3:10}[a['activity_priority']]
        tier={1:100,2:10,3:1}[project['contract_priority']]
        weighted_overrun_scaled+=tier*multiplier*activity_overrun[aid]
    for contract in sorted({a['contract_number'] for a in activities.values()}):
        ids=[aid for aid,a in activities.items() if a['contract_number']==contract]
        end=model.NewIntVar(1,horizon,f'contract_end:{contract}')
        model.AddMaxEquality(end,[completion[aid] for aid in ids]);contract_completion[contract]=end
        project=next(p for p in projects.values() if p['contract_number']==contract)
        offset=(origin-date.fromisoformat(project['planned_completion_date'])).days-1
        maximum=max(0,7*horizon+offset)
        contract_overrun[contract]=model.NewIntVar(0,maximum,f'contract_overrun:{contract}')
        model.AddMaxEquality(contract_overrun[contract],[0,7*end+offset])
        if scenario=='B':
            last_week=(date.fromisoformat(project['planned_completion_date'])-origin).days
            allowed=(last_week+1)//7
            enforce(end<=allowed,'planned_date')

    movement=[]
    for placement in sorted(options.baseline_placements,key=lambda r:(r.activity_id,r.access_seq)):
        key=placement.activity_id,placement.access_seq;changes=[]
        for name,var,value in [('week',W[key],placement.week),('physical',N[key],placement.physical_night),('local',L[key],placement.access_night),('eclo',E[key],placement.eclo)]:
            if value is None:continue
            changed=model.NewBoolVar(f'changed:{key}:{name}')
            model.Add(var!=value).OnlyEnforceIf(changed);model.Add(var==value).OnlyEnforceIf(changed.Not());changes.append(changed)
        moved=model.NewBoolVar(f'moved:{key}')
        if changes:model.AddMaxEquality(moved,changes)
        else:model.Add(moved==0)
        movement.append(moved)

    total_excess=sum(excess.values());total_eclo=sum(E.values())
    stable=sum((i+1)*(W[key]*(nights+1)*2003+N[key]*2003+L[key]*2+E[key]) for i,key in enumerate(sorted(W)))
    if scenario=='C':
        for value in excess.values():enforce(value<=1,'capacity')
        official=weighted_overrun_scaled+70*total_excess+50*total_eclo
        objectives=[('official_scenario_c_objective_scaled_10',official),('priority_weighted_overrun_scaled_10',weighted_overrun_scaled),
            ('excess_access_nights_total',total_excess),('eclo_nights_total',total_eclo),('raw_contract_overrun_days',sum(contract_overrun.values())),
            ('workload_over_delivery_scaled',sum(over_delivery.values())),('completion_weeks',sum(completion.values())+sum(contract_completion.values())),
            ('baseline_movements',sum(movement)),('stable_placement_rank',stable)]
    else:
        official=7*total_excess+5*total_eclo
        objectives=[('official_scenario_b_objective',official),('excess_access_nights_total',total_excess),
            ('eclo_nights_total',total_eclo),('workload_over_delivery_scaled',sum(over_delivery.values())),
            ('completion_weeks',sum(completion.values())+sum(contract_completion.values())),('baseline_movements',sum(movement)),
            ('stable_placement_rank',stable)]

    # A baseline is both a soft movement preference and a CP-SAT search hint.  Hint
    # every placement/channel variable whose value is implied by the baseline;
    # CP-SAT may repair the hint when it is valid for B but violates a C-only rule.
    baseline_by_key={(p.activity_id,p.access_seq):p for p in options.baseline_placements}
    baseline_by_week={(p.activity_id,p.week):p for p in options.baseline_placements}
    if baseline_by_key:
        for aid,a in activities.items():
            for k in range(1,a['total_accesses']+1):
                key=aid,k;placement=baseline_by_key.get(key)
                model.AddHint(active[key],int(placement is not None))
                model.AddHint(W[key],placement.week if placement else 0)
                model.AddHint(N[key],placement.physical_night if placement else 0)
                model.AddHint(L[key],(placement.access_night or 0) if placement else 0)
                model.AddHint(E[key],(placement.eclo or 0) if placement else 0)
                for w in weeks:
                    for n in night_ids:
                        model.AddHint(z[aid,k,w,n],int(placement is not None and placement.week==w and placement.physical_night==n))
            for w in weeks:
                placement=baseline_by_week.get((aid,w))
                model.AddHint(present[aid,w],int(placement is not None))
                model.AddHint(physical_week[aid,w],placement.physical_night if placement else 0)
                model.AddHint(local[aid,w],(placement.access_night or 0) if placement else 0)
                for n in night_ids:model.AddHint(x[aid,w,n],int(placement is not None and placement.physical_night==n))
    build_seconds=monotonic()-built_at;error=model.Validate()
    if error:return {'status':'MODEL_INVALID','placements':None,'diagnostics':[{'code':'model_invalid','message':error}], 'stages':[], 'solve_time_seconds':0,'primary_optimal':False,'lexicographic_complete':False,'build_seconds':build_seconds,'baseline_movement':0}
    model_variables=len(model.Proto().variables);model_constraints=len(model.Proto().constraints)
    initial_hints=len(model.Proto().solution_hint.vars)
    solved_at=monotonic();deterministic_used=0.0;candidate=None;status='UNKNOWN';primary_optimal=False;stages=[];diagnostics=[];movement_value=0;window_values={};cross_line=[];model_objective_value=None
    diagnostics.append({'code':'model_telemetry','variable_count':model_variables,'constraint_count':model_constraints,
        'incompatible_pair_count':len(data['pairs']),'hint_source':'baseline_placements' if initial_hints else None,
        'variables_hinted':initial_hints,'variables_not_hinted':model_variables-initial_hints,'complete_hint_supplied':initial_hints==model_variables})

    def stage_record(name,solver,result):
        response=solver.ResponseProto()
        return {'name':name,'status':solver.StatusName(result),'wall_seconds':solver.WallTime(),
            'deterministic_seconds':response.deterministic_time,'best_bound':solver.BestObjectiveBound(),
            'optimality_proven':result==cp_model.OPTIMAL,'branches':solver.NumBranches(),'conflicts':solver.NumConflicts(),
            'solution_info':response.solution_info,'stop_reason':solver.StatusName(result),
            'variable_count':model_variables,'constraint_count':model_constraints}

    def capture(solver):
        nonlocal candidate,movement_value,window_values,cross_line,model_objective_value
        candidate=[]
        for aid,a in activities.items():
            seq=0
            for k in range(1,a['total_accesses']+1):
                if solver.Value(active[aid,k]):
                    seq+=1;candidate.append(Placement(activity_id=aid,access_seq=seq,week=solver.Value(W[aid,k]),physical_night=solver.Value(N[aid,k]),access_night=solver.Value(L[aid,k]),eclo=solver.Value(E[aid,k])))
        candidate.sort(key=lambda r:(r.activity_id,r.access_seq));movement_value=sum(solver.Value(v) for v in movement)
        model_objective_value=int(solver.Value(official))
        if scenario=='C':
            window_values={line:{'active':bool(solver.Value(values['active'])),'start_week':solver.Value(values['start']) or None,
                'end_week':solver.Value(values['end']) or None,
                'activity_ids':sorted({key[0] for key in values['keys'] if solver.Value(E[key])})} for line,values in line_windows.items()}
            cross_line=sorted({key[0] for key in E if solver.Value(E[key]) and data['footprints'][key[0]]['lines']=={'ALP','BET'}})

    # Scenario C used to spend the entire budget proving bounds before finding an
    # incumbent.  A satisfaction pass first finds a hard-constraint-feasible plan;
    # its complete assignment then becomes the warm start for exact optimisation.
    if scenario=='C':
        model.ClearObjective();solver=cp_model.CpSolver();solver.parameters.num_search_workers=1
        solver.parameters.random_seed=options.random_seed;solver.parameters.max_time_in_seconds=options.time_limit_seconds
        solver.parameters.max_deterministic_time=options.deterministic_time_limit
        result=solver.Solve(model);deterministic_used+=solver.ResponseProto().deterministic_time
        stage=stage_record('hard_constraint_feasibility',solver,result);stages.append(stage)
        if result in (cp_model.OPTIMAL,cp_model.FEASIBLE):
            capture(solver);status='FEASIBLE';stage['value']=model_objective_value
            model.ClearHints()
            for index in range(model_variables):
                variable=model.get_int_var_from_proto_index(index);model.AddHint(variable,solver.Value(variable))
            diagnostics.append({'code':'complete_incumbent_hint','hint_source':'scenario_c_feasibility_stage',
                'variables_hinted':model_variables,'variables_not_hinted':0,'complete_hint_supplied':True,'hint_consistency':'solver_accepted'})
        elif result==cp_model.INFEASIBLE:
            status='INFEASIBLE'
        else:
            status=solver.StatusName(result)
            diagnostics.append({'code':'search_limit','message':'No incumbent within the configured feasibility budget. This does not prove infeasibility.'})

    objective_stages=[]
    for name,objective in objectives:
        wall=options.time_limit_seconds-(monotonic()-solved_at);det=options.deterministic_time_limit-deterministic_used
        if wall<=0 or det<=0:break
        model.Minimize(objective);solver=cp_model.CpSolver();solver.parameters.num_search_workers=1
        solver.parameters.random_seed=options.random_seed;solver.parameters.max_time_in_seconds=wall;solver.parameters.max_deterministic_time=det
        result=solver.Solve(model);stage_status=solver.StatusName(result);deterministic_used+=solver.ResponseProto().deterministic_time
        stage=stage_record(name,solver,result);stages.append(stage);objective_stages.append(stage)
        if result not in (cp_model.OPTIMAL,cp_model.FEASIBLE):
            if candidate is None:
                status=stage_status
                if result==cp_model.INFEASIBLE:
                    core=set(solver.SufficientAssumptionsForInfeasibility())
                    diagnostics.append({'code':'infeasible_constraint_core','constraint_families':[code for code,g in sorted(guards.items()) if g.Index() in core],
                        'message':'Sufficient (not necessarily minimal) assumption core; structural channeling constraints also apply.'})
            break
        value=int(solver.Value(objective));stage['value']=value
        stage['gap']=0 if result==cp_model.OPTIMAL else max(0,(value-solver.BestObjectiveBound())/max(abs(value),1))
        capture(solver)
        status='FEASIBLE'
        if name==objectives[0][0]:primary_optimal=result==cp_model.OPTIMAL
        if result!=cp_model.OPTIMAL:break
        model.Add(objective==value);model.ClearHints()
        for variable in list(W.values())+list(N.values())+list(L.values())+list(E.values()):model.AddHint(variable,solver.Value(variable))
    complete=len(objective_stages)==len(objectives) and all(s['status']=='OPTIMAL' for s in objective_stages)
    if complete:status='OPTIMAL'
    if candidate is None and status=='UNKNOWN':diagnostics.append({'code':'search_limit','message':'No incumbent within the configured solve budgets. This does not prove infeasibility.'})
    if candidate is None:diagnostics.append({'code':'physical_pair_constraints','incompatible_pairs':data['pairs']})
    return {'status':status,'placements':candidate,'diagnostics':diagnostics,'stages':stages,'primary_optimal':primary_optimal,
        'lexicographic_complete':complete,'solve_time_seconds':monotonic()-solved_at,'build_seconds':build_seconds,'baseline_movement':movement_value,
        'eclo_windows':window_values,'cross_line_eclo_activities':cross_line,'model_objective_value':model_objective_value}
