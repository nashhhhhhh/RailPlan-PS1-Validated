from uuid import UUID
from datetime import datetime
from fastapi import APIRouter,Query,HTTPException
from sqlalchemy import text
from app.dependencies import DB,Actor,Limit,Offset,writer
from app.contracts import Page,ScenarioOut,ScenarioDetail,ScenarioCreate,ScenarioClone,AssignmentEdit,Preview,Mutation,Capabilities,Comparison,Change
from app import repository as repo,services
from app.routers.requests import gate

router=APIRouter(prefix="/api/scenarios",tags=["Scenarios"])
RELATIONS={"team_ids":("scenario_teams","team_id","teams"),"engineer_ids":("scenario_engineers","engineer_id","engineers"),
           "asset_ids":("scenario_equipment","asset_id","equipment_assets"),"sector_ids":("scenario_sectors","sector_id","track_sectors")}
LOCK_FIELD={"team_ids":"team","engineer_ids":"engineers","asset_ids":"equipment","sector_ids":"sectors"}
LOCK_VALUE={"team_ids":"teams","engineer_ids":"engineers","asset_ids":"equipment","sector_ids":"sectors"}

def summary(db,sid):
    return db.execute(text("""SELECT to_jsonb(c)||jsonb_build_object('version',s.version,'run_id',s.run_id)
       FROM railplan.scenario_comparison c JOIN railplan.scenarios s ON s.id=c.id WHERE c.id=:id"""),{"id":sid}).scalar_one()

def assignments(db,sid):
    return repo.documents(db,"""SELECT to_jsonb(a)-'period'||jsonb_build_object(
      'team_ids',ARRAY(SELECT team_id FROM railplan.scenario_teams WHERE assignment_id=a.id),
      'engineer_ids',ARRAY(SELECT engineer_id FROM railplan.scenario_engineers WHERE assignment_id=a.id),
      'asset_ids',ARRAY(SELECT asset_id FROM railplan.scenario_equipment WHERE assignment_id=a.id),
      'sector_ids',ARRAY(SELECT sector_id FROM railplan.scenario_sectors WHERE assignment_id=a.id))
      FROM railplan.scenario_assignments a WHERE a.scenario_id=:id ORDER BY a.starts_at,a.id LIMIT 1001""",id=sid)

@router.get("",response_model=Page[ScenarioOut])
def listing(db:DB,actor:Actor,window_id:UUID,limit:Limit=50,offset:Offset=0):
    repo.window(db,window_id,actor)
    return repo.page(db,"""SELECT s.*,o.window_id FROM railplan.scenarios s JOIN railplan.optimisation_runs o ON o.id=s.run_id
       WHERE o.window_id=:w ORDER BY s.created_at DESC,s.id""",{"w":window_id},limit,offset)

@router.get("/compare",response_model=Comparison)
def compare(db:DB,actor:Actor,ids:list[UUID]=Query(min_length=2,max_length=5)):
    if len(set(ids))!=len(ids):raise HTTPException(422,"Duplicate scenarios")
    scopes=[repo.scenario(db,id,actor) for id in ids]
    if len({s["window_id"] for s in scopes})!=1:raise HTTPException(422,"Compare scenarios from the same engineering window")
    return {"scenarios":[summary(db,id) for id in ids],"conflict_resolution_comparable":False,
      "reason":"No compatible, verified baseline/rule snapshots are available"}

def new_scenario(db,actor,window_id,objective_id,name,source=None):
    repo.window(db,window_id,actor)
    services.require_ids(db,"optimisation_objectives",[objective_id])
    requested=repo.rows(db,"""SELECT * FROM railplan.maintenance_requests WHERE window_id=:w
       AND status_code NOT IN ('cancelled','rejected','completed') ORDER BY id LIMIT 1001 FOR UPDATE""",w=window_id)
    if len(requested)>1000:raise HTTPException(422,"Pilot limit: 1000 requests per draft")
    run=services.put(db,"optimisation_runs",window_id=window_id,objective_id=objective_id,requested_by=actor["id"],
      status="failed",input_snapshot=services.snapshot(db,window_id),error_message="Manual draft; solver not run")
    sid=services.put(db,"scenarios",run_id=run,name=name,provenance="manual_clone" if source else "manual")
    source_rows={x["request_id"]:x for x in repo.rows(db,"SELECT * FROM railplan.scenario_assignments WHERE scenario_id=:s",s=source)} if source else {}
    copied_requests=set()
    for r in requested:
        old=source_rows.get(r["id"])
        if source and not old:continue
        if old and old["request_version"]!=r["version"]:raise HTTPException(409,"Source scenario is stale; create a fresh baseline")
        copied_requests.add(r["id"])
        aid=services.put(db,"scenario_assignments",scenario_id=sid,request_id=r["id"],request_version=r["version"],
          original_start=r["requested_start"],original_end=r["requested_end"],starts_at=old["starts_at"] if old else r["requested_start"],
          ends_at=old["ends_at"] if old else r["requested_end"],reason="Copied draft for manual review",feasible=False)
        for key,(table,field,target) in RELATIONS.items():
            origin_table={"team_ids":"request_teams","engineer_ids":"request_engineers","asset_ids":"request_equipment_assets","sector_ids":"request_sectors"}[key]
            if old:
                values=db.execute(text(f"SELECT {field} FROM railplan.{table} WHERE assignment_id=:id"),{"id":old["id"]}).scalars()
            else:
                values=db.execute(text(f"SELECT {field} FROM railplan.{origin_table} WHERE request_id=:id"),{"id":r["id"]}).scalars()
            for value in values:services.put(db,table,assignment_id=aid,**{field:value})
    # Preserve source-specific locks in the clone with explicit ownership/history.
    if source:
        for lock in repo.rows(db,"""SELECT * FROM railplan.request_locks WHERE scenario_id=:s AND released_at IS NULL
          AND (expires_at IS NULL OR expires_at>now())""",s=source):
            if lock["request_id"] not in copied_requests:continue
            lid=services.put(db,"request_locks",request_id=lock["request_id"],scenario_id=sid,scope="scenario",
              locked_by=lock["locked_by"],reason="Cloned scope: "+lock["reason"],locked_values=lock["locked_values"],expires_at=lock["expires_at"])
            for f in db.execute(text("SELECT field FROM railplan.lock_fields WHERE lock_id=:id"),{"id":lock["id"]}).scalars():
                services.put(db,"lock_fields",lock_id=lid,field=f)
    repo.event(db,actor,"scenario.created","scenarios",sid,"Editable draft created; validation required")
    return {"id":sid,"status":"draft","version":repo.scenario(db,sid,actor)["version"],"validation_status":"unvalidated"}

@router.post("",status_code=201,response_model=Mutation)
def create(payload:ScenarioCreate,db:DB,actor:Actor):
    writer(actor);gate(db,actor)
    return new_scenario(db,actor,payload.window_id,payload.objective_id,payload.name)

@router.post("/{scenario_id}/clone",status_code=201,response_model=Mutation)
def clone(scenario_id:UUID,payload:ScenarioClone,db:DB,actor:Actor):
    writer(actor);gate(db,actor)
    s=repo.scenario(db,scenario_id,actor,True);repo.version(s,payload.expected_version)
    obj=db.execute(text("SELECT objective_id FROM railplan.optimisation_runs WHERE id=:r"),{"r":s["run_id"]}).scalar_one()
    return new_scenario(db,actor,s["window_id"],obj,payload.name,scenario_id)

@router.get("/{scenario_id}",response_model=ScenarioDetail)
def detail(scenario_id:UUID,db:DB,actor:Actor):
    s=repo.scenario(db,scenario_id,actor)
    values=assignments(db,scenario_id)
    if len(values)>1000:raise HTTPException(422,"Scenario exceeds pilot detail limit")
    return {"summary":summary(db,scenario_id),"assignments":values,
      "changes":repo.documents(db,"SELECT to_jsonb(c) FROM railplan.change_replay c WHERE scenario_id=:s ORDER BY replay_order LIMIT 1000",s=scenario_id),
      "analysis":repo.latest_analysis(db,s["window_id"],scenario_id),"capabilities":Capabilities()}

@router.get("/{scenario_id}/changes",response_model=Page[Change])
def changes(scenario_id:UUID,db:DB,actor:Actor,limit:Limit=50,offset:Offset=0):
    repo.scenario(db,scenario_id,actor)
    return repo.page(db,"SELECT * FROM railplan.change_replay WHERE scenario_id=:s ORDER BY replay_order",{"s":scenario_id},limit,offset)

def basic_issues(r,w,a,s,payload,locks):
    issues=[]
    if s["status"]!="draft":issues.append("Only draft scenarios are editable")
    if a["request_version"]!=r["version"]:issues.append("Request snapshot is stale")
    if r["status_code"] in ("cancelled","rejected","completed"):issues.append("Request is no longer schedulable")
    if r.get("flexibility")=="fixed" and (payload.starts_at,payload.ends_at)!=(r["requested_start"],r["requested_end"]):
        issues.append("Requested timing is fixed")
    duration=(payload.ends_at-payload.starts_at).total_seconds()/60
    if not r["min_duration_minutes"]<=duration<=r["max_duration_minutes"]:issues.append("Duration outside request limits")
    if not (r["earliest_start"]<=payload.starts_at and payload.ends_at<=r["latest_finish"]
            and w["starts_at"]<=payload.starts_at and payload.ends_at<=w["ends_at"]):issues.append("Timing outside allowed window")
    for lock in locks:
        values=lock["locked_values"]
        if "timing" in lock["fields"]:
            start=datetime.fromisoformat(values["starts_at"]);end=datetime.fromisoformat(values["ends_at"])
            if (payload.starts_at,payload.ends_at)!=(start,end):issues.append("Timing is locked")
        for key,field in LOCK_FIELD.items():
            incoming=getattr(payload,key)
            if incoming is not None and field in lock["fields"]:
                if set(map(str,incoming))!=set(values.get(LOCK_VALUE[key]) or []):issues.append(field+" is locked")
    return issues

def evaluate(db,actor,sid,aid,payload):
    s=repo.scenario(db,sid,actor,True);repo.version(s,payload.expected_version)
    a=services.one(db,"SELECT * FROM railplan.scenario_assignments WHERE id=:id AND scenario_id=:s",id=aid,s=sid)
    if not a:raise HTTPException(404,"Assignment not found")
    r=repo.request(db,a["request_id"],actor,True);w=repo.window(db,s["window_id"],actor)
    for key,(_,_,target) in RELATIONS.items():
        values=getattr(payload,key)
        if values is None:continue
        if key=="sector_ids":services.require_ids(db,target,values,"AND line_id=:line",line=w["line_id"])
        else:services.require_ids(db,target,values,"AND department_id IN (SELECT id FROM railplan.departments WHERE operator_id=:op)",op=actor["operator_id"])
    effective=payload.model_copy()
    for key,(table,field,_) in RELATIONS.items():
        if getattr(effective,key) is None:
            setattr(effective,key,list(db.execute(text(f"SELECT {field} FROM railplan.{table} WHERE assignment_id=:id"),{"id":aid}).scalars()))
    issues=basic_issues(r,w,a,s,effective,repo.active_locks(db,r["id"],sid))
    # An existing possession/isolation plan would otherwise become silently inconsistent.
    if db.execute(text("SELECT 1 FROM railplan.possession_assignments WHERE assignment_id=:a LIMIT 1"),{"a":aid}).scalar():
        issues.append("Assignment belongs to a possession; clone to a new manual draft before editing")
    return s,a,issues

@router.post("/{scenario_id}/assignments/{assignment_id}/preview",response_model=Preview)
def preview(scenario_id:UUID,assignment_id:UUID,payload:AssignmentEdit,db:DB,actor:Actor):
    writer(actor);gate(db,actor)
    s,a,issues=evaluate(db,actor,scenario_id,assignment_id,payload)
    return {"basic_valid":not issues,"issues":issues,"starts_at":payload.starts_at,"ends_at":payload.ends_at,
      "scenario_version":s["version"],"complete_conflict_validation_performed":False,"analysis_required":True}

@router.patch("/{scenario_id}/assignments/{assignment_id}",response_model=Mutation)
def edit(scenario_id:UUID,assignment_id:UUID,payload:AssignmentEdit,db:DB,actor:Actor):
    writer(actor);gate(db,actor)
    s,a,issues=evaluate(db,actor,scenario_id,assignment_id,payload)
    if issues:raise HTTPException(409,"; ".join(issues))
    db.execute(text("""UPDATE railplan.scenario_assignments SET starts_at=:start,ends_at=:end,reason=:reason,
       feasible=false WHERE id=:id"""),{"start":payload.starts_at,"end":payload.ends_at,"reason":payload.reason,"id":assignment_id})
    for key,(table,field,_) in RELATIONS.items():
        values=getattr(payload,key)
        if values is None:continue
        db.execute(text(f"DELETE FROM railplan.{table} WHERE assignment_id=:id"),{"id":assignment_id})
        for value in values:services.put(db,table,assignment_id=assignment_id,**{field:value})
    # Materialized metrics were calculated on an older assignment set.
    db.execute(text("DELETE FROM railplan.scenario_metrics WHERE scenario_id=:s"),{"s":scenario_id})
    repo.event(db,actor,"scenario.assignment_updated","scenarios",scenario_id,payload.reason)
    return {"id":scenario_id,"status":"draft","version":repo.scenario(db,scenario_id,actor)["version"],"validation_status":"unvalidated"}
