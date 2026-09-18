from uuid import UUID
from fastapi import APIRouter,HTTPException,Query
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from app.dependencies import DB,Actor,Limit,Offset,writer,role
from app.contracts import Page,Entity,WindowOut,Capabilities,CommandCentre,ReadEvents,ReadResult,ReferenceData,TimelineItem,ApprovalHistory,ConflictOut
from app.schemas import AnalysisCreate,OptimisationCreate,ApprovalSubmit,ApprovalDecision
from app import repository as repo,services,conflict_engine
from app.models import Base
from app.routers.scenarios import summary
from app.routers.requests import gate

router=APIRouter(prefix="/api",tags=["Command centre and coordination"])
CAPS=Capabilities(conflict_analysis_available=True)
SCORE_SUMMARY="""(SELECT jsonb_build_object('id',s.id,'policy_id',s.policy_id,
 'created_at',s.created_at,'result',s.result,'engine_version',s.engine_version,
 'freshness',CASE WHEN s.source_revision=(SELECT revision FROM railplan.scoring_source_revision WHERE id=1)
 AND s.engine_version='railplan-scoring/1.0.0' THEN 'fresh' ELSE 'stale' END)
 FROM railplan.conflict_scores s WHERE s.conflict_id=c.id ORDER BY s.created_at DESC,s.id DESC LIMIT 1)"""

@router.get("/capabilities",response_model=Capabilities)
def capabilities(actor:Actor):return CAPS

@router.get("/engineering-windows",response_model=Page[WindowOut])
def windows(db:DB,actor:Actor,limit:Limit=50,offset:Offset=0):
    return repo.page(db,"SELECT w.* FROM railplan.engineering_windows w WHERE "+repo.WINDOW_SCOPE+
                     " ORDER BY w.starts_at DESC,w.id",{"operator":actor["operator_id"]},limit,offset)

@router.get("/engineering-windows/{window_id}",response_model=WindowOut)
def window(window_id:UUID,db:DB,actor:Actor):return repo.window(db,window_id,actor)

@router.get("/reference-data",response_model=ReferenceData)
def reference(db:DB,actor:Actor):
    result={"priorities":["normal","high","urgent"],"capabilities":CAPS,"limit_per_collection":200,
            "resource_lists_url":"/api/teams","collections_may_be_truncated":True}
    for name in ("work_types","request_statuses","equipment_types","skills","optimisation_objectives"):
        result[name]=repo.documents(db,f"SELECT to_jsonb(x) FROM railplan.{name} x ORDER BY x.code,x.id LIMIT 200")
    result["teams"]=repo.documents(db,"""SELECT to_jsonb(x) FROM railplan.teams x JOIN railplan.departments d ON d.id=x.department_id
       WHERE d.operator_id=:op ORDER BY x.name,x.id LIMIT 200""",op=actor["operator_id"])
    result["isolation_zones"]=repo.documents(db,"""SELECT to_jsonb(x)-'geom' FROM railplan.isolation_zones x
      JOIN railplan.networks n ON n.id=x.network_id WHERE n.operator_id=:op ORDER BY x.code,x.id LIMIT 200""",op=actor["operator_id"])
    return result

@router.get("/timeline/{window_id}",response_model=list[TimelineItem])
def timeline(window_id:UUID,db:DB,actor:Actor,scenario_id:UUID|None=None,limit:Limit=200,offset:Offset=0):
    repo.window(db,window_id,actor)
    if scenario_id and repo.scenario(db,scenario_id,actor)["window_id"]!=window_id:raise HTTPException(422,"Scenario/window mismatch")
    # Compatibility: preserve array shape, expose bounded page controls.
    return repo.documents(db,"""SELECT to_jsonb(t) FROM railplan.engineering_timeline t WHERE window_id=:w
      AND (t.scenario_id IS NOT NULL OR EXISTS(SELECT 1 FROM railplan.maintenance_requests r
        WHERE r.id=t.request_id AND r.status_code NOT IN ('cancelled','rejected','completed')))
      AND scenario_id IS NOT DISTINCT FROM CAST(:s AS uuid) ORDER BY starts_at,request_id LIMIT :limit OFFSET :offset""",
      w=window_id,s=scenario_id,limit=limit,offset=offset)

@router.get("/command-centre/{window_id}",response_model=CommandCentre)
def command(window_id:UUID,db:DB,actor:Actor,scenario_id:UUID|None=None):
    w=repo.window(db,window_id,actor)
    selected=repo.scenario(db,scenario_id,actor) if scenario_id else None
    if selected and selected["window_id"]!=window_id:raise HTTPException(422,"Scenario/window mismatch")
    requests=repo.documents(db,"SELECT to_jsonb(r)-'requested_period' FROM railplan.request_details r WHERE window_id=:w ORDER BY requested_start,id LIMIT 501",w=window_id)
    times=repo.documents(db,"""SELECT to_jsonb(t) FROM railplan.engineering_timeline t WHERE window_id=:w
      AND (t.scenario_id IS NOT NULL OR EXISTS(SELECT 1 FROM railplan.maintenance_requests r
        WHERE r.id=t.request_id AND r.status_code NOT IN ('cancelled','rejected','completed')))
      AND scenario_id IS NOT DISTINCT FROM CAST(:s AS uuid) ORDER BY starts_at,request_id LIMIT 501""",w=window_id,s=scenario_id)
    scenarios=repo.documents(db,"""SELECT to_jsonb(s) FROM railplan.scenarios s JOIN railplan.optimisation_runs o ON o.id=s.run_id
       WHERE o.window_id=:w ORDER BY s.created_at DESC,s.id LIMIT 51""",w=window_id)
    analysis=repo.latest_analysis(db,window_id,scenario_id)
    conflicts=None
    if analysis and analysis["status"]=="completed":
        conflicts=repo.documents(db,"SELECT to_jsonb(c)||jsonb_build_object('freshness','unknown','latest_score',"+SCORE_SUMMARY+") FROM railplan.coordination_queue c WHERE analysis_run_id=:id ORDER BY detected_at,id LIMIT 201",id=analysis["id"])
    return {"window":w,"requests":requests[:500],"timeline":times[:500],"analysis":analysis,
      "conflicts":conflicts[:200] if conflicts is not None else None,"scenarios":scenarios[:50],
      "selected_scenario_id":scenario_id,"selected_scenario_version":selected["version"] if selected else None,
      "capabilities":CAPS,"truncated":len(requests)>500 or len(times)>500 or len(scenarios)>50 or (conflicts is not None and len(conflicts)>200)}

@router.post("/analyses",status_code=201)
def analyse(payload:AnalysisCreate,db:DB,actor:Actor):
    writer(actor);gate(db,actor);repo.window(db,payload.window_id,actor)
    if payload.scenario_id and repo.scenario(db,payload.scenario_id,actor)["window_id"]!=payload.window_id:raise HTTPException(422,"Scenario/window mismatch")
    analysis_id=services.put(db,"analysis_runs",window_id=payload.window_id,
      scenario_id=payload.scenario_id,requested_by=actor["id"],input_snapshot={},rule_snapshot=[])
    return conflict_engine.run_conflict_analysis(db,analysis_id)

@router.post("/optimisation-runs")
def optimise(payload:OptimisationCreate,db:DB,actor:Actor):
    writer(actor);repo.window(db,payload.window_id,actor)
    raise HTTPException(503,"Optimisation worker is not configured; no job was accepted")

def run_detail(db,actor,table,id):
    row=services.one(db,f"SELECT * FROM railplan.{table} WHERE id=:id",id=id)
    if not row:raise HTTPException(404,"Run not found")
    repo.window(db,row["window_id"],actor)
    value=repo.document(db,table,id)
    value["freshness"]="unknown"
    value["worker_available"]=False
    # No unverifiable inputs or parameters are interpreted as a safety result.
    if table=="optimisation_runs":
        value["execution_status"]="not_run" if value.get("error_message","") and "solver" in value["error_message"].lower() else value["status"]
        value["solver_outcome"]=None
        value["scenario_ids"]=list(db.execute(text("SELECT id FROM railplan.scenarios WHERE run_id=:id ORDER BY created_at,id"),{"id":id}).scalars())
    return value

@router.get("/analyses/{analysis_id}")
def analysis(analysis_id:UUID,db:DB,actor:Actor):
    conflict_engine.require_analysis(db,analysis_id,actor)
    return conflict_engine.analysis_summary(db,analysis_id)

@router.get("/analyses/{analysis_id}/conflicts")
def analysis_conflicts(analysis_id:UUID,db:DB,actor:Actor):
    conflict_engine.require_analysis(db,analysis_id,actor)
    return conflict_engine.conflict_details(db,analysis_id)

@router.get("/optimisation-runs/{run_id}",response_model=Entity)
def run(run_id:UUID,db:DB,actor:Actor):return run_detail(db,actor,"optimisation_runs",run_id)

@router.get("/conflicts",response_model=Page[ConflictOut])
def conflicts(db:DB,actor:Actor,analysis_id:UUID,limit:Limit=50,offset:Offset=0,
              lens:str|None=Query(None,pattern="^(Possession|Isolation|Manpower|Equipment|Compatibility|Dependencies|Resources|Review)$")):
    run_detail(db,actor,"analysis_runs",analysis_id)
    return repo.page(db,"SELECT "+SCORE_SUMMARY+" AS latest_score,"+"""c.*,r.version AS rule_version,'unknown'::text AS freshness FROM railplan.coordination_queue c
       JOIN railplan.rule_definitions r ON r.id=c.rule_id WHERE c.analysis_run_id=:a
       AND (CAST(:lens AS text) IS NULL OR c.lens=:lens) ORDER BY c.detected_at,c.id""",{"a":analysis_id,"lens":lens},limit,offset)

@router.get("/conflicts/{conflict_id}",response_model=ConflictOut)
def conflict(conflict_id:UUID,db:DB,actor:Actor):
    c=services.one(db,"SELECT * FROM railplan.coordination_queue WHERE id=:id",id=conflict_id)
    if not c:raise HTTPException(404,"Conflict not found")
    repo.window(db,c["window_id"],actor)
    result=repo.document(db,"coordination_queue",conflict_id)
    rule=repo.document(db,"rule_definitions",c["rule_id"])
    result.update(rule=rule,freshness="unknown",can_certify_current_schedule=False)
    result["version"]=db.execute(text("SELECT version FROM railplan.conflicts WHERE id=:id"),{"id":conflict_id}).scalar_one()
    result["latest_score"]=db.execute(text("SELECT "+SCORE_SUMMARY+" FROM railplan.conflicts c WHERE c.id=:id"),{"id":conflict_id}).scalar_one()
    for name in ("teams","engineers","equipment","sectors","isolations"):
        result[name]=repo.documents(db,f"SELECT to_jsonb(x) FROM railplan.conflict_{name} x WHERE conflict_id=:id ORDER BY id LIMIT 200",id=conflict_id)
    return result

@router.get("/scenarios/{scenario_id}/approval",response_model=ApprovalHistory)
def scenario_approval(scenario_id:UUID,db:DB,actor:Actor,limit:Limit=50,offset:Offset=0):
    repo.scenario(db,scenario_id,actor)
    return {"available":False,"reason":"Complete validation and publishing services are not integrated",
      "history":repo.page(db,"SELECT * FROM railplan.approval_summary WHERE scenario_id=:s ORDER BY created_at DESC,id",{"s":scenario_id},limit,offset)}

@router.get("/approvals/{approval_id}",response_model=Entity)
def approval(approval_id:UUID,db:DB,actor:Actor):
    a=services.one(db,"SELECT * FROM railplan.approval_summary WHERE id=:id",id=approval_id)
    if not a:raise HTTPException(404,"Approval not found")
    repo.scenario(db,a["scenario_id"],actor)
    value=repo.document(db,"approval_summary",approval_id)
    value["decisions"]=repo.documents(db,"SELECT to_jsonb(d) FROM railplan.approval_decisions d WHERE approval_request_id=:id ORDER BY created_at,id LIMIT 200",id=approval_id)
    return value

@router.post("/scenarios/{scenario_id}/approval")
def submit_approval(scenario_id:UUID,payload:ApprovalSubmit,db:DB,actor:Actor):
    writer(actor);s=repo.scenario(db,scenario_id,actor);repo.version(s,payload.expected_version)
    raise HTTPException(501,"Operational approval is disabled until complete validation and publication services exist")

@router.post("/approvals/{approval_id}/decisions")
def decide(approval_id:UUID,payload:ApprovalDecision,db:DB,actor:Actor):
    role(actor,"safety_reviewer","approver")
    approval(approval_id,db,actor)
    raise HTTPException(501,"Operational approval decisions are disabled")

ACTIVITY_SCOPE="""e.actor_id IN (SELECT u.id FROM railplan.users u JOIN railplan.departments d
 ON d.id=u.department_id WHERE d.operator_id=:op)"""

@router.get("/activity",response_model=Page[Entity])
def activity(db:DB,actor:Actor,limit:Limit=50,offset:Offset=0):
    return repo.page(db,"""SELECT e.*,er.read_at FROM railplan.operational_activity e
       LEFT JOIN railplan.event_reads er ON er.event_id=e.id AND er.user_id=:u WHERE """+ACTIVITY_SCOPE+
       " ORDER BY e.created_at DESC,e.id",{"op":actor["operator_id"],"u":actor["id"]},limit,offset)

@router.post("/activity/read",response_model=ReadResult)
def mark_read(payload:ReadEvents,db:DB,actor:Actor):
    gate(db,actor)
    table=Base.metadata.tables["railplan.event_reads"]
    for eid in payload.event_ids:
        if not services.one(db,"SELECT e.id FROM railplan.activity_events e WHERE e.id=:id AND "+ACTIVITY_SCOPE,id=eid,op=actor["operator_id"]):
            raise HTTPException(404,"Activity event not found")
    for eid in payload.event_ids:
        db.execute(pg_insert(table).values(event_id=eid,user_id=actor["id"]).on_conflict_do_nothing(index_elements=["event_id","user_id"]))
    return {"marked_read":len(payload.event_ids)}
