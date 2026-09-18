"""Persistence services only. No solver, safety validator, or operational publishing."""
from datetime import datetime, timezone
from uuid import UUID, uuid4
from fastapi import HTTPException
from sqlalchemy import text, insert
from sqlalchemy.orm import Session
from app.models import Base
from app.queries import QUERIES

def put(db, table, **values):
    return db.execute(insert(Base.metadata.tables["railplan."+table]).values(**values).returning(
        Base.metadata.tables["railplan."+table].c.id)).scalar_one()

def one(db, sql, **params):
    return db.execute(text(sql),params).mappings().one_or_none()

def require_window(db, window_id, actor):
    w=one(db,"""SELECT w.*,d.operator_id FROM railplan.engineering_windows w
    JOIN railplan.lines l ON l.id=w.line_id JOIN railplan.networks n ON n.id=l.network_id
    JOIN railplan.departments d ON d.operator_id=n.operator_id
    WHERE w.id=:id AND d.id=:department""",id=window_id,department=actor["department_id"])
    if w is None:
        raise HTTPException(404,"Engineering window not found")
    return w

def require_request(db, request_id, actor):
    r=one(db,"SELECT * FROM railplan.maintenance_requests WHERE id=:id FOR UPDATE",id=request_id)
    if r is None:
        raise HTTPException(404,"Request not found")
    require_window(db,r["window_id"],actor)
    return r

def require_scenario(db, scenario_id, actor):
    s=one(db,"""SELECT s.*,o.window_id FROM railplan.scenarios s
    JOIN railplan.optimisation_runs o ON o.id=s.run_id WHERE s.id=:id FOR UPDATE OF s""",id=scenario_id)
    if s is None:
        raise HTTPException(404,"Scenario not found")
    require_window(db,s["window_id"],actor)
    return s

def require_ids(db, table, ids, clause="", **params):
    for value in ids:
        if not one(db,f"SELECT id FROM railplan.{table} WHERE id=:id "+clause,id=value,**params):
            raise HTTPException(422,f"Unknown or out-of-scope {table} ID")

def create_request(db, payload, actor):
    w=require_window(db,payload.window_id,actor)
    if payload.requested_start<w["starts_at"] or payload.requested_end>w["ends_at"]:
        raise HTTPException(422,"Requested work must fit the engineering window")
    require_ids(db,"work_types",[payload.work_type_id])
    require_ids(db,"track_sectors",payload.sector_ids,"AND line_id=:line",line=w["line_id"])
    for table,ids in (("teams",payload.team_ids),("engineers",payload.engineer_ids)):
        require_ids(db,table,ids,"AND department_id=:dep",dep=actor["department_id"])
    net=db.execute(text("SELECT network_id FROM railplan.lines WHERE id=:id"),{"id":w["line_id"]}).scalar_one()
    require_ids(db,"workzones",payload.workzone_ids,"AND network_id=:net",net=net)
    require_ids(db,"isolation_zones",[x.isolation_zone_id for x in payload.isolations],"AND network_id=:net",net=net)
    require_ids(db,"skills",[x.skill_id for x in payload.skills])
    require_ids(db,"equipment_types",[x.type_id for x in payload.equipment])
    values=payload.model_dump(exclude={"sector_ids","team_ids","engineer_ids","workzone_ids","equipment","skills","isolations","submit"})
    rid=put(db,"maintenance_requests",**values,department_id=actor["department_id"],created_by=actor["id"],
            submitted_by=actor["id"] if payload.submit else None,
            submitted_at=datetime.now(timezone.utc) if payload.submit else None,
            status_code="submitted" if payload.submit else "draft")
    for table,field,ids in (("request_sectors","sector_id",payload.sector_ids),
                            ("request_teams","team_id",payload.team_ids),
                            ("request_engineers","engineer_id",payload.engineer_ids),
                            ("request_workzones","workzone_id",payload.workzone_ids)):
        for value in ids:
            put(db,table,request_id=rid,**{field:value})
    for table,items in (("request_equipment_requirements",payload.equipment),("request_skills",payload.skills),
                        ("request_isolations",payload.isolations)):
        for item in items:
            put(db,table,request_id=rid,**item.model_dump())
    put(db,"activity_events",actor_id=actor["id"],event_type="request.submitted" if payload.submit else "request.created",
        message="Maintenance request submitted; validation pending" if payload.submit else "Draft maintenance request created",
        entity_type="maintenance_requests",entity_id=rid)
    return {"id":rid,"status":"submitted" if payload.submit else "draft","version":1,"validation_status":"unvalidated"}

def snapshot(db,window_id):
    # Consistent statement-level snapshot for queued work. Future worker must validate
    # relevant resources/rules against a full versioned input graph before approval.
    return db.execute(text("""SELECT jsonb_build_object(
      'requests',(SELECT jsonb_agg(to_jsonb(r)) FROM railplan.request_details r WHERE window_id=:w),
      'active_locks',(SELECT jsonb_agg(to_jsonb(l)) FROM railplan.request_locks l
        JOIN railplan.maintenance_requests r ON r.id=l.request_id WHERE r.window_id=:w
        AND l.released_at IS NULL AND (l.expires_at IS NULL OR l.expires_at>now())),
      'complete_solver_input',false)"""),{"w":window_id}).scalar_one()

def create_lock(db,rid,payload,actor):
    r=require_request(db,rid,actor)
    if r["version"]!=payload.expected_version:
        raise HTTPException(409,"Request changed; reload before locking")
    scenario_id=payload.scenario_id
    if scenario_id:
        s=require_scenario(db,scenario_id,actor)
        if s["window_id"]!=r["window_id"] or s["status"]!="draft":
            raise HTTPException(409,"Lock requires a draft scenario in the same window")
        assignment=one(db,"SELECT * FROM railplan.scenario_assignments WHERE scenario_id=:s AND request_id=:r",
                       s=scenario_id,r=rid)
        if not assignment:
            raise HTTPException(422,"Request is not assigned in this scenario")
    if payload.expires_at and payload.expires_at<=datetime.now(timezone.utc):
        raise HTTPException(422,"Lock expiry must be in the future")
    existing=one(db,"""SELECT id FROM railplan.request_locks WHERE request_id=:r
       AND scenario_id IS NOT DISTINCT FROM CAST(:s AS uuid) AND released_at IS NULL
       AND (expires_at IS NULL OR expires_at>now())""",r=rid,s=scenario_id)
    if existing:
        raise HTTPException(409,"An active lock already exists in this scope")
    # Preserve concrete selected assignments, not only a boolean.
    if scenario_id:
        values=db.execute(text("""SELECT jsonb_build_object(
          'starts_at',a.starts_at,'ends_at',a.ends_at,
          'teams',(SELECT jsonb_agg(team_id) FROM railplan.scenario_teams WHERE assignment_id=a.id),
          'engineers',(SELECT jsonb_agg(engineer_id) FROM railplan.scenario_engineers WHERE assignment_id=a.id),
          'equipment',(SELECT jsonb_agg(asset_id) FROM railplan.scenario_equipment WHERE assignment_id=a.id),
          'sectors',(SELECT jsonb_agg(sector_id) FROM railplan.scenario_sectors WHERE assignment_id=a.id))
          FROM railplan.scenario_assignments a WHERE a.id=:a"""),{"a":assignment["id"]}).scalar_one()
    else:
        values=db.execute(text("""SELECT jsonb_build_object(
          'starts_at',r.requested_start,'ends_at',r.requested_end,
          'teams',(SELECT jsonb_agg(team_id) FROM railplan.request_teams WHERE request_id=r.id),
          'engineers',(SELECT jsonb_agg(engineer_id) FROM railplan.request_engineers WHERE request_id=r.id),
          'equipment',(SELECT jsonb_agg(asset_id) FROM railplan.request_equipment_assets WHERE request_id=r.id),
          'sectors',(SELECT jsonb_agg(sector_id) FROM railplan.request_sectors WHERE request_id=r.id))
          FROM railplan.maintenance_requests r WHERE r.id=:r"""),{"r":rid}).scalar_one()
    lid=put(db,"request_locks",request_id=rid,scenario_id=scenario_id,locked_by=actor["id"],
            scope="scenario" if scenario_id else "request",reason=payload.reason,locked_values=values,expires_at=payload.expires_at)
    for field in set(payload.fields):
        put(db,"lock_fields",lock_id=lid,field=field)
    return {"id":lid,"status":"locked"}

def submit_approval(db,sid,payload,actor):
    s=require_scenario(db,sid,actor)
    if s["version"]!=payload.expected_version:
        raise HTTPException(409,"Scenario changed; reload")
    # Deliberate safety boundary: this deliverable has no complete validation worker.
    raise HTTPException(501,"Approval submission is disabled until a complete, version-aware safety validator is integrated")

def record_decision(db,approval_id,payload,actor):
    a=one(db,"SELECT * FROM railplan.approval_requests WHERE id=:id",id=approval_id)
    if not a:
        raise HTTPException(404,"Approval request not found")
    require_scenario(db,a["scenario_id"],actor)
    raise HTTPException(501,"Operational approval decisions are disabled until the validation/publishing service is integrated")
