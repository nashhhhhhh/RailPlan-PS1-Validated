from uuid import UUID
from datetime import datetime,timezone
from fastapi import APIRouter,Query,HTTPException
from sqlalchemy import text
from app.dependencies import DB,Actor,Limit,Offset,writer
from app.contracts import Page,RequestOut,Mutation,RequestPatch,ExpectedVersion,CancelRequest,ReleaseLock,Entity
from app.schemas import RequestCreate,LockCreate
from app import repository as repo,services

router=APIRouter(prefix="/api",tags=["Requests and locks"])

def gate(db,actor):
    # Same operator lock used by all API mutations; safe simple pilot concurrency policy.
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),{"key":str(actor["operator_id"])})

@router.get("/maintenance-requests",response_model=Page[RequestOut])
def listing(db:DB,actor:Actor,limit:Limit=50,offset:Offset=0,window_id:UUID|None=None,
            sector_id:UUID|None=None,station_id:UUID|None=None,team_id:UUID|None=None,
            status:str|None=Query(None,max_length=40),priority:str|None=Query(None,pattern="^(normal|high|urgent)$"),
            search:str|None=Query(None,max_length=200),sort:str=Query("time",pattern="^(time|code|updated)$")):
    clauses=["d.operator_id=:operator"];params={"operator":actor["operator_id"]}
    for key,val in (("window_id",window_id),("status_code",status),("priority",priority)):
        if val is not None:clauses.append(f"r.{key}=:{key}");params[key]=val
    if sector_id:
        clauses.append("EXISTS(SELECT 1 FROM railplan.request_sectors x WHERE x.request_id=r.id AND x.sector_id=:sector)")
        params["sector"]=sector_id
    if station_id:
        clauses.append("""EXISTS(SELECT 1 FROM railplan.request_sectors x JOIN railplan.track_sectors s ON s.id=x.sector_id
          WHERE x.request_id=r.id AND (s.from_station_id=:station OR s.to_station_id=:station))""")
        params["station"]=station_id
    if team_id:
        clauses.append("EXISTS(SELECT 1 FROM railplan.request_teams x WHERE x.request_id=r.id AND x.team_id=:team)")
        params["team"]=team_id
    if search:
        clauses.append("(r.title ILIKE :search OR r.request_code ILIKE :search)")
        params["search"]="%"+search+"%"
    order={"time":"r.requested_start,r.id","code":"r.request_code,r.id","updated":"r.updated_at DESC,r.id"}[sort]
    return repo.page(db,"SELECT r.* FROM railplan.request_details r JOIN railplan.departments d ON d.id=r.department_id WHERE "+
                     " AND ".join(clauses)+" ORDER BY "+order,params,limit,offset)

@router.post("/maintenance-requests",status_code=201,response_model=Mutation)
def create(payload:RequestCreate,db:DB,actor:Actor):
    writer(actor);gate(db,actor)
    return services.create_request(db,payload,actor)

@router.get("/maintenance-requests/{request_id}",response_model=RequestOut)
def detail(request_id:UUID,db:DB,actor:Actor):
    repo.request(db,request_id,actor)
    value=repo.document(db,"request_details",request_id)
    for field,table in (("engineers","request_engineers"),("skills","request_skills"),
       ("isolations","request_isolations"),("workzones","request_workzones")):
        value[field]=repo.documents(db,f"SELECT to_jsonb(x) FROM railplan.{table} x WHERE request_id=:id ORDER BY id",id=request_id)
    return value

@router.patch("/maintenance-requests/{request_id}",response_model=Mutation)
def patch(request_id:UUID,payload:RequestPatch,db:DB,actor:Actor):
    writer(actor);gate(db,actor)
    r=repo.request(db,request_id,actor,True);repo.version(r,payload.expected_version)
    if r["status_code"]!="draft":raise HTTPException(409,"Only draft requests may be edited; clone intent or edit a scenario")
    relation_keys={"sector_ids","team_ids","engineer_ids","workzone_ids","equipment","skills","isolations"}
    all_edits=payload.model_dump(exclude_unset=True,exclude={"expected_version"})
    edits={k:v for k,v in all_edits.items() if k not in relation_keys}
    if repo.active_locks(db,request_id) and set(edits).intersection(
      {"requested_start","requested_end","earliest_start","latest_finish","min_duration_minutes","max_duration_minutes"}):
        raise HTTPException(409,"Release the applicable request lock before changing timing")
    merged={**r,**edits}
    duration=(merged["requested_end"]-merged["requested_start"]).total_seconds()/60
    if not 0<merged["min_duration_minutes"]<=duration<=merged["max_duration_minutes"]:
        raise HTTPException(422,"Invalid duration limits")
    w=repo.window(db,r["window_id"],actor)
    if "work_type_id" in edits:services.require_ids(db,"work_types",[edits["work_type_id"]])
    net=db.execute(text("SELECT network_id FROM railplan.lines WHERE id=:id"),{"id":w["line_id"]}).scalar_one()
    for key,target in (("team_ids","teams"),("engineer_ids","engineers")):
        if key in all_edits:services.require_ids(db,target,all_edits[key],"AND department_id=:d",d=r["department_id"])
    if "sector_ids" in all_edits:services.require_ids(db,"track_sectors",all_edits["sector_ids"],"AND line_id=:line",line=w["line_id"])
    if "workzone_ids" in all_edits:services.require_ids(db,"workzones",all_edits["workzone_ids"],"AND network_id=:n",n=net)
    for key,target,column in (("equipment","equipment_types","type_id"),("skills","skills","skill_id"),("isolations","isolation_zones","isolation_zone_id")):
        if key in all_edits:
            clause="AND network_id=:n" if key=="isolations" else ""
            services.require_ids(db,target,[x[column] for x in all_edits[key]],clause,**({"n":net} if clause else {}))
    locked_fields={f for lock in repo.active_locks(db,request_id) for f in lock["fields"]}
    for key,field in (("team_ids","team"),("engineer_ids","engineers"),("equipment","equipment"),("sector_ids","sectors")):
        if key in all_edits and field in locked_fields:raise HTTPException(409,"Release the "+field+" lock before editing")
    if not (merged["earliest_start"]<=merged["requested_start"]<merged["requested_end"]<=merged["latest_finish"]
            and w["starts_at"]<=merged["requested_start"] and merged["requested_end"]<=w["ends_at"]):
        raise HTTPException(422,"Timing falls outside allowed bounds")
    # Field names are restricted by the Pydantic model, not arbitrary client keys.
    setter=",".join(f"{key}=:{key}" for key in edits) or "updated_at=now()"
    db.execute(text("UPDATE railplan.maintenance_requests SET "+setter+" WHERE id=:id"),{**edits,"id":request_id})
    for key,table,field in (("sector_ids","request_sectors","sector_id"),("team_ids","request_teams","team_id"),
      ("engineer_ids","request_engineers","engineer_id"),("workzone_ids","request_workzones","workzone_id"),
      ("equipment","request_equipment_requirements",None),("skills","request_skills",None),("isolations","request_isolations",None)):
        if key not in all_edits:continue
        db.execute(text(f"DELETE FROM railplan.{table} WHERE request_id=:id"),{"id":request_id})
        for item in all_edits[key]:
            services.put(db,table,request_id=request_id,**({field:item} if field else item))
    version=repo.request(db,request_id,actor)["version"]
    repo.event(db,actor,"request.updated","maintenance_requests",request_id,"Draft request updated")
    return {"id":request_id,"status":"draft","version":version}

@router.post("/maintenance-requests/{request_id}/submit",response_model=Mutation)
def submit(request_id:UUID,payload:ExpectedVersion,db:DB,actor:Actor):
    writer(actor);gate(db,actor)
    r=repo.request(db,request_id,actor,True);repo.version(r,payload.expected_version)
    if r["status_code"]!="draft":raise HTTPException(409,"Request is not a draft")
    db.execute(text("""UPDATE railplan.maintenance_requests SET status_code='submitted',
       submitted_by=:actor,submitted_at=now() WHERE id=:id"""),{"actor":actor["id"],"id":request_id})
    repo.event(db,actor,"request.submitted","maintenance_requests",request_id,"Request submitted; analysis required")
    return {"id":request_id,"status":"submitted","version":r["version"]+1,"validation_status":"unvalidated"}

@router.post("/maintenance-requests/{request_id}/cancel",response_model=Mutation)
def cancel(request_id:UUID,payload:CancelRequest,db:DB,actor:Actor):
    writer(actor);gate(db,actor)
    r=repo.request(db,request_id,actor,True);repo.version(r,payload.expected_version)
    if r["status_code"] not in ("draft","submitted","under_review","conflict_detected","scenario_proposed"):
        raise HTTPException(409,"Request cannot be cancelled in this state")
    if db.execute(text("""SELECT 1 FROM railplan.scenario_assignments a JOIN railplan.scenarios s ON s.id=a.scenario_id
      WHERE a.request_id=:id AND s.status IN ('pending_review','approved') LIMIT 1"""),{"id":request_id}).scalar():
        raise HTTPException(409,"Withdraw the reviewed schedule through its authorized workflow first")
    db.execute(text("""UPDATE railplan.maintenance_requests SET status_code='cancelled',cancelled_at=now(),
      cancellation_reason=:reason WHERE id=:id"""),{"id":request_id,"reason":payload.reason})
    repo.event(db,actor,"request.cancelled","maintenance_requests",request_id,"Request cancelled: "+payload.reason)
    return {"id":request_id,"status":"cancelled","version":r["version"]+1}

@router.get("/maintenance-requests/{request_id}/locks",response_model=Page[Entity])
def locks(request_id:UUID,db:DB,actor:Actor,limit:Limit=50,offset:Offset=0):
    repo.request(db,request_id,actor)
    return repo.page(db,"""SELECT l.*,ARRAY(SELECT field FROM railplan.lock_fields f WHERE f.lock_id=l.id) AS fields
      FROM railplan.request_locks l WHERE l.request_id=:r ORDER BY l.created_at DESC,l.id""",{"r":request_id},limit,offset)

@router.post("/maintenance-requests/{request_id}/locks",status_code=201,response_model=Mutation)
def lock(request_id:UUID,payload:LockCreate,db:DB,actor:Actor):
    writer(actor);gate(db,actor)
    repo.request(db,request_id,actor)
    result=services.create_lock(db,request_id,payload,actor)
    repo.event(db,actor,"request.locked","maintenance_requests",request_id,payload.reason)
    return result

@router.post("/locks/{lock_id}/release",response_model=Mutation)
def release(lock_id:UUID,payload:ReleaseLock,db:DB,actor:Actor):
    writer(actor);gate(db,actor)
    row=services.one(db,"SELECT * FROM railplan.request_locks WHERE id=:id FOR UPDATE",id=lock_id)
    if not row:raise HTTPException(404,"Lock not found")
    repo.request(db,row["request_id"],actor)
    if row["locked_by"]!=actor["id"] and "administrator" not in actor["roles"]:
        raise HTTPException(403,"Only the lock owner or administrator may release it")
    if row["released_at"] is None:
        db.execute(text("UPDATE railplan.request_locks SET released_at=now(),released_by=:u WHERE id=:id"),{"u":actor["id"],"id":lock_id})
        repo.event(db,actor,"lock.released","maintenance_requests",row["request_id"],payload.reason)
    return {"id":lock_id,"status":"released"}
