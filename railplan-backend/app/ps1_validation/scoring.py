"""Published numeric formulas; provisional completion/aggregation conventions."""
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from .contracts import violation

def money(value):
    return str(Decimal(value).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))

def score(dataset, state, results, scenario):
    activities,projects=state['activities'],state['projects']
    start=date.fromisoformat(dataset['parameters']['horizon_start'])
    dates={aid:start+timedelta(weeks=week,days=-1) for aid,week in state['completion_weeks'].items()}
    weighted=Decimal(0); activity_metrics=[]; violations=[]
    contract_activities=defaultdict(list)
    for aid,a in sorted(activities.items()):
        p=projects[a['contract_number'],a['activity_type']]
        contract_activities[a['contract_number']].append(aid)
        complete=dates.get(aid)
        overrun=max(0,(complete-date.fromisoformat(p['planned_completion_date'])).days) if complete else None
        weight=Decimal({1:100,2:10,3:1}[p['contract_priority']])*Decimal({1:'1.3',2:'1.2',3:'1.0'}[a['activity_priority']])
        cost=weight*overrun if overrun is not None else None
        if cost is not None: weighted+=cost
        activity_metrics.append({'activity_id':aid,'contract_number':a['contract_number'],
            'completion_date':complete.isoformat() if complete else None,'overrun_days':overrun,
            'weight':money(weight),'weighted_overrun':money(cost) if cost is not None else None})
        if scenario=='B' and overrun:
            violations.append(violation('planned_date','Scenario B planned completion date exceeded',
                activities=[aid],contracts=[a['contract_number']],week=state['completion_weeks'][aid],
                completion_date=complete.isoformat(),planned_completion_date=p['planned_completion_date'],overrun_days=overrun))
    supplied=defaultdict(list)
    for row in results: supplied[row['contract_number']].append(row)
    for contract in sorted(set(supplied)-{p['contract_number'] for p in projects.values()}):
        violations.append(violation('unknown_reference','Unknown RESULTS contract',contracts=[contract]))
    raw=0; early=0; contracts_overrunning=0; tiers={'1':0,'2':0,'3':0}; contract_metrics=[]
    for contract in sorted({p['contract_number'] for p in projects.values()}):
        records=sorted((p for p in projects.values() if p['contract_number']==contract),key=lambda p:p['activity_type'])
        ids=sorted(contract_activities[contract])
        consistent=len({(p['contract_priority'],p['planned_completion_date']) for p in records})==1
        if not consistent:
            violations.append(violation('results_consistency','Contract types disagree on target date or priority',contracts=[contract],records=records))
        complete=max((dates[aid] for aid in ids),default=None) if ids and all(aid in dates for aid in ids) else None
        planned=date.fromisoformat(records[0]['planned_completion_date'])
        overrun=max(0,(complete-planned).days) if complete and consistent else None
        derived={'contract_number':contract,'simulated_completion_date':complete.isoformat() if complete else None,'overrun_days':overrun}
        contract_metrics.append(derived)
        if overrun is not None:
            raw+=overrun; tiers[str(records[0]['contract_priority'])]+=overrun
            contracts_overrunning+=int(overrun>0); early+=max(0,(planned-complete).days)
        rows=supplied[contract]
        if len(rows)!=1 or complete is None or not consistent or any(rows[0][k]!=derived[k] for k in ('simulated_completion_date','overrun_days')):
            violations.append(violation('results_consistency','RESULTS must contain one accurate completed-contract summary',
                activities=ids,contracts=[contract],derived=derived,submitted=rows))
    excess=sum(r['excess'] for r in state['capacity_hotspots'])
    eclo=sum(r['eclo'] for r in state['access'])
    diagnostic=(weighted if scenario!='B' else Decimal(0))+(Decimal(7*excess+5*eclo) if scenario!='A' else Decimal(0))
    return {'overrun_days_total':raw,'contracts_overrunning':contracts_overrunning,'earliness_days_total':early,
        'priority_overrun':tiers,'priority_weighted_overrun':money(weighted),'excess_access_nights_total':excess,
        'excess_penalty':money(7*excess),'eclo_nights_total':eclo,'eclo_penalty':money(5*eclo),
        'diagnostic_objective':money(diagnostic),'activity_components':activity_metrics,'contract_results':contract_metrics,
        'metrics_complete':len(dates)==len(activities),'nights_scheduled':len(state['access']),
        'formula':{'A':'priority_weighted_overrun','B':'7 * excess_access_nights_total + 5 * eclo_nights_total',
                   'C':'priority_weighted_overrun + 7 * excess_access_nights_total + 5 * eclo_nights_total'}[scenario]}, violations
