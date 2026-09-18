"""Integer CP-SAT model. No validator, CSV parsing, database or approval logic."""
from collections import defaultdict
from datetime import date
from time import monotonic
from ortools.sat.python import cp_model
from .contracts import Placement

def solve(dataset, data, options):
    started = monotonic()
    model = cp_model.CpModel()
    activities,projects = data['activities'],data['projects']
    horizon,nights = data['horizon'],options.physical_nights_per_week
    weeks = range(1,horizon+1)
    night_ids = range(1,nights+1)
    guards = {}
    def enforce(expression, code):
        if code not in guards:
            guards[code] = model.NewBoolVar('rule:'+code)
            model.AddAssumption(guards[code])
        model.Add(expression).OnlyEnforceIf(guards[code])
    x,p,night,local,W,N,L,completion = {},{},{},{},{},{},{},{}
    by_project = defaultdict(list)
    by_location = defaultdict(list)
    for aid,a in activities.items():
        by_project[a['contract_number'],a['activity_type']].append(aid)
        for loc in sorted(data['footprints'][aid]['occupied']): by_location[loc].append(aid)
        for w in weeks:
            p[aid,w] = model.NewBoolVar(f'present:{aid}:{w}')
            night[aid,w] = model.NewIntVar(0,nights,f'night:{aid}:{w}')
            local[aid,w] = model.NewIntVar(0,projects[a['contract_number'],a['activity_type']]['number_of_maximum_access_per_week'],f'local:{aid}:{w}')
            for n in night_ids: x[aid,w,n] = model.NewBoolVar(f'x:{aid}:{w}:{n}')
            model.Add(sum(x[aid,w,n] for n in night_ids)==p[aid,w])
            model.Add(night[aid,w]==sum(n*x[aid,w,n] for n in night_ids))
            if w < a['planned_start_week']: enforce(p[aid,w]==0,'planned_start')
        choices = defaultdict(list)
        for k in range(1,a['total_accesses']+1):
            W[aid,k] = model.NewIntVar(1,horizon,f'week:{aid}:{k}')
            N[aid,k] = model.NewIntVar(1,nights,f'physical:{aid}:{k}')
            cap = projects[a['contract_number'],a['activity_type']]['number_of_maximum_access_per_week']
            L[aid,k] = model.NewIntVar(1,cap,f'access_night:{aid}:{k}')
            index = model.NewIntVar(0,horizon-1,f'index:{aid}:{k}')
            model.Add(index==W[aid,k]-1)
            model.AddElement(index,[night[aid,w] for w in weeks],N[aid,k])
            model.AddElement(index,[local[aid,w] for w in weeks],L[aid,k])
            selectors=[]
            for w in weeks:
                y=model.NewBoolVar(f'sequence:{aid}:{k}:{w}')
                model.Add(W[aid,k]==w).OnlyEnforceIf(y)
                selectors.append(y); choices[w].append(y)
            model.AddExactlyOne(selectors)
            if k>1: enforce(W[aid,k]>W[aid,k-1],'access_sequence')
        for w in weeks: enforce(sum(choices[w])==p[aid,w],'workload')
        completion[aid]=W[aid,a['total_accesses']]
    for aid,a in activities.items():
        pred=a['predecessor_activity_id']
        if pred: enforce(W[aid,1]>completion[pred],'dependency')
    # A local access index denotes a used physical night for this contract/type only.
    # Distinct unused negative sentinels allow AllDifferent without inventing nights.
    for key,ids in sorted(by_project.items()):
        project=projects[key]; cap=project['number_of_maximum_access_per_week']
        for w in weeks:
            used=[]; labels=[]
            for n in night_ids:
                u=model.NewBoolVar(f'used:{key}:{w}:{n}')
                model.AddMaxEquality(u,[x[aid,w,n] for aid in ids]); used.append(u)
                label=model.NewIntVarFromDomain(cp_model.Domain.FromValues([-n]+list(range(1,cap+1))),f'label:{key}:{w}:{n}')
                model.Add(label==-n).OnlyEnforceIf(u.Not())
                model.Add(label>=1).OnlyEnforceIf(u)
                labels.append(label)
                enforce(sum(x[aid,w,n] for aid in ids)<=project['number_of_workfronts'],'workfront')
            model.AddAllDifferent(labels)
            enforce(sum(used)<=cap,'weekly_allocation')
            for aid in ids: model.AddElement(night[aid,w],[0]+labels,local[aid,w])
    # A single location/night possession is shared by every activity occupying it.
    for loc,ids in sorted(by_location.items()):
        pm=[aid for aid in ids if projects[activities[aid]['contract_number'],activities[aid]['activity_type']]['access_type']=='PM']
        pc=[aid for aid in ids if projects[activities[aid]['contract_number'],activities[aid]['activity_type']]['access_type']=='PC']
        for w in weeks:
            slots=[]
            for n in night_ids:
                slot=model.NewBoolVar(f'possession:{loc}:{w}:{n}')
                model.AddMaxEquality(slot,[x[aid,w,n] for aid in ids]); slots.append(slot)
                enforce(sum(x[aid,w,n] for aid in pc)<=1,'possession_mix')
                enforce(sum(x[aid,w,n] for aid in pm)<=1,'possession_mix')
                enforce(sum(x[aid,w,n] for aid in ids)<=4-3*sum(x[aid,w,n] for aid in pm),'possession_mix')
            enforce(sum(slots)<=data['supply'][loc],'capacity')
    for pair in data['pairs']:
        aid,bid=pair['activity_ids']
        for w in weeks:
            for n in night_ids:
                # One pair constraint; diagnostics retain every applicable collision family.
                enforce(x[aid,w,n]+x[bid,w,n]<=1,'physical_closure')
    for placement in sorted(options.locked_placements,key=lambda p:(p.activity_id,p.access_seq)):
        key=placement.activity_id,placement.access_seq
        code=f'lock:{key[0]}:{key[1]}'
        enforce(W[key]==placement.week,code)
        enforce(N[key]==placement.physical_night,code)
        if placement.access_night is not None: enforce(L[key]==placement.access_night,code)
    start=date.fromisoformat(dataset['parameters']['horizon_start'])
    activity_overrun={}; contract_completion={}; contract_overrun={}
    primary=[]
    for aid,a in activities.items():
        project=projects[a['contract_number'],a['activity_type']]
        target=(date.fromisoformat(project['planned_completion_date'])-start).days
        over=model.NewIntVar(0,max(0,7*horizon-1-target),f'overrun:{aid}')
        model.AddMaxEquality(over,[0,7*completion[aid]-1-target]); activity_overrun[aid]=over
        weight={1:100,2:10,3:1}[project['contract_priority']]*{1:13,2:12,3:10}[a['activity_priority']]
        primary.append(weight*over)
    for contract in sorted({a['contract_number'] for a in activities.values()}):
        ids=[aid for aid,a in activities.items() if a['contract_number']==contract]
        end=model.NewIntVar(1,horizon,f'contract_end:{contract}')
        model.AddMaxEquality(end,[completion[aid] for aid in ids]); contract_completion[contract]=end
        project=next(p for p in projects.values() if p['contract_number']==contract)
        target=(date.fromisoformat(project['planned_completion_date'])-start).days
        over=model.NewIntVar(0,max(0,7*horizon-1-target),f'contract_overrun:{contract}')
        model.AddMaxEquality(over,[0,7*end-1-target]); contract_overrun[contract]=over
    movement=[]
    for placement in sorted(options.baseline_placements,key=lambda p:(p.activity_id,p.access_seq)):
        key=placement.activity_id,placement.access_seq
        changes=[]
        for name,var,value in [('week',W[key],placement.week),('physical',N[key],placement.physical_night),('local',L[key],placement.access_night)]:
            if value is None: continue
            diff=model.NewBoolVar(f'changed:{key}:{name}')
            model.Add(var!=value).OnlyEnforceIf(diff); model.Add(var==value).OnlyEnforceIf(diff.Not())
            changes.append(diff)
        moved=model.NewBoolVar(f'moved:{key}'); model.AddMaxEquality(moved,changes); movement.append(moved)
    objectives=[('weighted_overrun_scaled_10',sum(primary)),('raw_contract_overrun_days',sum(contract_overrun.values())),
                ('completion_weeks',sum(completion.values())+sum(contract_completion.values())),
                ('baseline_movements',sum(movement)),
                ('stable_placement_rank',sum((i+1)*(W[key]*(nights+1)*1001+N[key]*1001+L[key]) for i,key in enumerate(sorted(W))))]
    build_seconds=monotonic()-started
    stages=[]; candidate=None; deterministic_used=0.0; primary_optimal=False
    status='UNKNOWN'; diagnostics=[]
    error=model.Validate()
    if error: return dict(status='MODEL_INVALID',placements=None,diagnostics=[{'code':'model_invalid','message':error}],stages=[],solve_time_seconds=0,primary_optimal=False,lexicographic_complete=False,build_seconds=build_seconds)
    solve_started=monotonic()
    for name,objective in objectives:
        wall_remaining=options.time_limit_seconds-(monotonic()-solve_started)
        det_remaining=options.deterministic_time_limit-deterministic_used
        if wall_remaining<=0 or det_remaining<=0: break
        model.Minimize(objective)
        solver=cp_model.CpSolver()
        solver.parameters.num_search_workers=1
        solver.parameters.random_seed=options.random_seed
        solver.parameters.max_time_in_seconds=wall_remaining
        solver.parameters.max_deterministic_time=det_remaining
        result=solver.Solve(model)
        stage_status=solver.StatusName(result)
        deterministic_used+=solver.ResponseProto().deterministic_time
        stage={'name':name,'status':stage_status,'wall_seconds':solver.WallTime(),'deterministic_seconds':solver.ResponseProto().deterministic_time,'best_bound':solver.BestObjectiveBound()}
        stages.append(stage)
        if result not in (cp_model.OPTIMAL,cp_model.FEASIBLE):
            if candidate is None:
                status=stage_status
                if result==cp_model.INFEASIBLE:
                    core=set(solver.SufficientAssumptionsForInfeasibility())
                    diagnostics.append({'code':'infeasible_constraint_core','constraint_families':[code for code,g in sorted(guards.items()) if g.Index() in core],
                        'message':'Sufficient (not necessarily minimal) assumption core; structural channeling constraints also apply.'})
            break
        value=int(solver.Value(objective))
        stage['value']=value
        candidate=[Placement(activity_id=aid,access_seq=k,week=solver.Value(W[aid,k]),physical_night=solver.Value(N[aid,k]),access_night=solver.Value(L[aid,k])) for aid,k in sorted(W)]
        status='FEASIBLE'
        if name==objectives[0][0]: primary_optimal=result==cp_model.OPTIMAL
        if result!=cp_model.OPTIMAL: break
        model.Add(objective==value) # Secondary stages cannot sacrifice any primary unit.
        model.ClearHints()
        for variable in list(W.values())+list(N.values())+list(L.values()): model.AddHint(variable,solver.Value(variable))
    complete=len(stages)==len(objectives) and all(s['status']=='OPTIMAL' for s in stages)
    if complete: status='OPTIMAL'
    if candidate is None and status=='UNKNOWN': diagnostics.append({'code':'search_limit','message':'No incumbent within the configured solve budgets. This does not prove infeasibility.'})
    if candidate is None:
        diagnostics.append({'code':'physical_pair_constraints','incompatible_pairs':data['pairs']})
    return dict(status=status,placements=candidate,diagnostics=diagnostics,stages=stages,primary_optimal=primary_optimal,
                lexicographic_complete=complete,solve_time_seconds=monotonic()-solve_started,build_seconds=build_seconds)
