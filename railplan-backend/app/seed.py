"""Idempotent synthetic fixtures. Run after alembic upgrade head."""
from datetime import datetime, timedelta
from uuid import uuid5, NAMESPACE_URL
from sqlalchemy import text
from app.database import engine

def uid(key):
    return uuid5(NAMESPACE_URL, "railplan-demo/" + key)

def seed(conn):
    def add(table, key, **values):
        values = {"id": uid(key), **values}
        # Table/column names below are fixed developer literals, never user input.
        columns = ",".join(values)
        params = ",".join(":"+x for x in values)
        conn.execute(text(f"INSERT INTO railplan.{table} ({columns}) VALUES ({params}) ON CONFLICT DO NOTHING"), values)
        return uid(key)

    # Do not rewrite existing demo scenarios: repeat runs leave planner state untouched.
    if conn.execute(text("SELECT 1 FROM railplan.operators WHERE id=:id"), {"id":uid("operator")}).scalar():
        return
    op = add("operators", "operator", code="DEMO", name="Synthetic Rail Operator")
    dep = add("departments", "department", operator_id=op, name="Demo Engineering")
    actor = add("users", "planner", department_id=dep, auth_subject="demo-planner", display_name="Demo Planner")
    reviewer = add("users", "reviewer", department_id=dep, auth_subject="demo-reviewer", display_name="Demo Reviewer")
    for role in ("planner","engineering_supervisor","safety_reviewer","approver","administrator","viewer"):
        rid=add("roles","role/"+role,code=role,name=role.replace("_"," ").title())
        if role=="planner":
            add("user_roles","planner-role",user_id=actor,role_id=rid)
        if role in ("safety_reviewer","approver"):
            add("user_roles","reviewer-role/"+role,user_id=reviewer,role_id=rid)
    net=add("networks","network",operator_id=op,code="DEMO-SG",name="Synthetic Singapore Network")
    line=add("lines","line",network_id=net,code="NSL-DEMO",name="North–South Line (demo)")
    station_names=["Yio Chu Kang","Ang Mo Kio","Bishan","Braddell","Toa Payoh","Novena","Newton","Orchard"]
    stations=[]
    for i,name in enumerate(station_names,15):
        st=add("stations","station/"+name,network_id=net,name=name,geometry_source="unverified: no operational coordinates supplied")
        stations.append(st)
        add("line_stations","line-station/"+name,line_id=line,station_id=st,code=f"NS{i}",sequence_no=i)
    sectors={}
    for i in range(7):
        name=station_names[i]+"–"+station_names[i+1]
        sec=add("track_sectors","sector/"+name,line_id=line,from_station_id=stations[i],to_station_id=stations[i+1],
                code=f"DEMO-NS-{i+1}",name=name,geometry_source="unverified: no track geometry supplied")
        sectors[name]=sec
        add("tracks","track/"+name,sector_id=sec,code="demo-track",direction="unspecified")
    origin=datetime.fromisoformat("2026-09-14T00:30:00+08:00")
    finish=origin+timedelta(hours=4)
    window=add("engineering_windows","window",line_id=line,name="Demo night 14 September",
               service_date=origin.date(),starts_at=origin,ends_at=finish)
    for kind in ("permitted_work","service_shutdown"):
        add("window_periods","period/"+kind,window_id=window,kind=kind,starts_at=origin,ends_at=finish)
    for name,sec in sectors.items():
        add("sector_availability","availability/"+name,window_id=window,sector_id=sec,available=True,starts_at=origin,ends_at=finish)
    for status in ("draft","submitted","under_review","conflict_detected","scenario_proposed","approved","scheduled","in_progress","completed","cancelled","rejected"):
        add("request_statuses","status/"+status,code=status)
    skill=add("skills","skill/signalling",code="SIGNAL",name="Synthetic signalling certification")
    team_names=["Team Alpha","Team Bravo","Team Charlie","Team Delta","Team Echo","Team Foxtrot","Vehicle crew","Power team"]
    teams={}
    for name in team_names:
        team=add("teams","team/"+name,department_id=dep,name=name)
        teams[name]=team
        eng=add("engineers","engineer/"+name,department_id=dep,employee_code="DEMO-"+name.replace(" ","-"),name=name+" engineer")
        add("team_memberships","member/"+name,team_id=team,engineer_id=eng,starts_at=origin-timedelta(days=30),ends_at=finish+timedelta(days=30))
        add("engineer_skills","cert/"+name,engineer_id=eng,skill_id=skill,certificate_reference="SYNTHETIC",
            starts_at=origin-timedelta(days=30),ends_at=finish+timedelta(days=30))
        add("engineer_availability","eng-available/"+name,engineer_id=eng,available=True,starts_at=origin,ends_at=finish)
        add("team_availability","team-available/"+name,team_id=team,available=True,starts_at=origin,ends_at=finish)
    equipment={}
    for name in ("Inspection kit","Rail crane","Test meter","Drain pump","Inspection vehicle","Isolation panel"):
        typ=add("equipment_types","eqtype/"+name,code=name.upper().replace(" ","_"),name=name)
        asset=add("equipment_assets","asset/"+name,department_id=dep,type_id=typ,asset_code="DEMO-"+name.replace(" ","-"),name=name+" 01")
        add("equipment_availability","eq-available/"+name,asset_id=asset,available=True,starts_at=origin,ends_at=finish)
        equipment[name]=(typ,asset)
    rows=[
      ("MR-018","Signal inspection","Bishan–Braddell","Team Alpha",15,60,"Inspection kit",[15,15,15]),
      ("MR-024","Rail renewal","Bishan–Braddell","Team Bravo",45,75,"Rail crane",[90,75,90]),
      ("MR-031","Cable inspection","Braddell–Toa Payoh","Team Charlie",30,60,"Test meter",[30,30,30]),
      ("MR-037","Point machine test","Braddell–Toa Payoh","Team Bravo",140,45,"Test meter",[170,160,170]),
      ("MR-040","Drainage clearance","Toa Payoh–Novena","Team Delta",10,50,"Drain pump",[10,10,10]),
      ("MR-045","Track walk","Toa Payoh–Novena","Team Echo",110,65,"Inspection kit",[110,110,100]),
      ("MR-042","Platform inspection","Novena–Newton","Team Alpha",45,45,"Inspection kit",[90,90,90]),
      ("MR-048","Safety handback","Bishan–Braddell","Team Alpha",200,30,"Inspection kit",[200,200,200]),
      ("MR-050","Geometry run","Bishan–Braddell","Vehicle crew",110,45,"Inspection vehicle",[165,165,180]),
      ("MR-052","Vehicle transfer","Novena–Newton","Vehicle crew",135,30,"Inspection vehicle",[210,210,150]),
      ("MR-054","P4 isolation window","Bishan–Braddell","Power team",0,145,"Isolation panel",[0,0,0]),
      ("MR-056","Station systems","Newton–Orchard","Team Foxtrot",65,60,"Test meter",[65,65,65]),
    ]
    requests={}
    for code,title,sector,team,start,duration,eq,options in rows:
        wt=add("work_types","type/"+title,code=title.upper().replace(" ","_"),name=title)
        req=add("maintenance_requests",code,request_code=code,window_id=window,department_id=dep,work_type_id=wt,
                title=title,description="Synthetic fixture from current RailPlan UI",status_code="submitted",
                requested_start=origin+timedelta(minutes=start),requested_end=origin+timedelta(minutes=start+duration),
                min_duration_minutes=duration,max_duration_minutes=duration,earliest_start=origin,latest_finish=finish,
                created_by=actor,submitted_by=actor,submitted_at=origin-timedelta(days=1))
        requests[code]=req
        add("request_sectors",code+"/sector",request_id=req,sector_id=sectors[sector])
        add("request_teams",code+"/team",request_id=req,team_id=teams[team])
        add("request_equipment_requirements",code+"/eq",request_id=req,type_id=equipment[eq][0])
        if eq=="Inspection vehicle":
            add("request_equipment_assets",code+"/asset",request_id=req,asset_id=equipment[eq][1])
    add("request_skills","signal-skill",request_id=requests["MR-018"],skill_id=skill)
    zone=add("isolation_zones","P4",network_id=net,code="DEMO-P4",name="Synthetic P4 zone")
    add("isolation_zone_sectors","P4-sector",isolation_zone_id=zone,sector_id=sectors["Bishan–Braddell"])
    add("request_isolations","P4-isolated",request_id=requests["MR-054"],isolation_zone_id=zone,required_state="isolated")
    add("request_isolations","P4-restored",request_id=requests["MR-050"],isolation_zone_id=zone,required_state="restored")
    for code in ("finish_to_start","start_to_start","finish_to_finish","requires_isolation","requires_restoration","requires_handback","requires_testing"):
        add("dependency_types","dependency/"+code,code=code,name=code.replace("_"," "))
    add("request_dependencies","renewal-handback",predecessor_id=requests["MR-024"],successor_id=requests["MR-048"],
        dependency_type_id=uid("dependency/finish_to_start"),lag_minutes=15,explanation="Synthetic testing buffer")
    rules=[
      ("POS-001","Overlapping possession","Possession","critical",["MR-018","MR-024"],"Synthetic exclusive-sector overlap: 01:15–01:45."),
      ("ISO-004","Isolation dependency","Isolation","critical",["MR-054","MR-050"],"Geometry run needs restored power but overlaps the synthetic P4 isolation."),
      ("RES-002","Engineer double-booking","Manpower","high",["MR-018","MR-042"],"Team Alpha overlaps between 01:15 and 01:45."),
      ("EQP-003","Shared inspection vehicle","Equipment","high",["MR-050","MR-052"],"Inspection vehicle overlaps between 02:45 and 03:05."),
      ("DEP-005","Handback sequence review","Dependencies","information",["MR-024","MR-048"],"Manual demonstration warning, not a computed violation."),
    ]
    run=add("analysis_runs","analysis",window_id=window,requested_by=actor,status="completed",
            input_snapshot='{"synthetic": true}',rule_snapshot='{"source":"UI fixtures; not executed rules"}',completed_at=origin)
    for code,title,lens,severity,members,explanation in rules:
        rule=add("rule_definitions","rule/"+code,code=code,name=title,category=lens,severity=severity,blocking=code!="DEP-005")
        cf=add("conflicts","conflict/"+code,conflict_code="DEMO-"+code,analysis_run_id=run,rule_id=rule,
               title=title,explanation=explanation,severity=severity,detection_method="synthetic")
        for reqcode in members:
            add("conflict_requests","conflict/"+code+"/"+reqcode,conflict_id=cf,request_id=requests[reqcode])
    objectives=[("minimum_disruption","Minimum disruption"),("closest_timing","Closest requested timing"),("resource_efficiency","Resource efficiency")]
    for i,(code,name) in enumerate(objectives):
        obj=add("optimisation_objectives","objective/"+code,code=code,name=name)
        run=add("optimisation_runs","run/"+code,window_id=window,objective_id=obj,requested_by=actor,
                status="failed",input_snapshot='{"synthetic":true}',error_message="No solver executed: UI preset only")
        scenario=add("scenarios","scenario/"+code,run_id=run,name=name,provenance="ui_preset")
        for reqcode,title,sector,team,start,duration,eq,options in rows:
            assignment=add("scenario_assignments",code+"/"+reqcode,scenario_id=scenario,request_id=requests[reqcode],
                request_version=1,original_start=origin+timedelta(minutes=start),original_end=origin+timedelta(minutes=start+duration),
                starts_at=origin+timedelta(minutes=options[i]),ends_at=origin+timedelta(minutes=options[i]+duration),
                reason="UI preset; no feasibility guarantee",feasible=False)
            add("scenario_sectors",code+"/"+reqcode+"/sector",assignment_id=assignment,sector_id=sectors[sector])
            add("scenario_teams",code+"/"+reqcode+"/team",assignment_id=assignment,team_id=teams[team])
            if eq=="Inspection vehicle":
                add("scenario_equipment",code+"/"+reqcode+"/asset",assignment_id=assignment,asset_id=equipment[eq][1])
    workflow=add("approval_workflows","workflow",operator_id=op,name="Demo safety and planning review")
    for i,role in enumerate(("safety_reviewer","approver"),1):
        add("approval_stages","stage/"+role,workflow_id=workflow,required_role_id=uid("role/"+role),sequence_no=i,name=role)
    add("activity_events","welcome",actor_id=actor,event_type="demo.seeded",
        message="12 synthetic requests imported. Scenarios are unvalidated UI presets.")

if __name__ == "__main__":
    with engine().begin() as conn:
        seed(conn)
        from app.demo_rules import configure_demo_rules
        configure_demo_rules(conn)
    print("Synthetic fixtures ready (idempotent).")
