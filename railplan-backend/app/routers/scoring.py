"""Transactional scoring of existing conflicts, not conflict detection."""
import json
from app import scoring_models  # Register additive mappings with shared metadata.
from uuid import UUID
from fastapi import APIRouter, HTTPException
from sqlalchemy import text
from app.dependencies import DB, Actor, Limit, Offset, role
from app.contracts import Entity, Page
from app import repository as repo, services
from app.routers.requests import gate
from app.scoring import PolicyCreate, ScoreCreate, ScoreResult, evaluate, fingerprint, canonical, ENGINE_VERSION

router = APIRouter(prefix="/api", tags=["Conflict severity scoring"])

class ScoreOut(Entity):
    conflict_id: UUID
    policy_id: UUID
    input_fingerprint: str
    policy_fingerprint: str
    source_revision: int
    engine_version: str
    result: ScoreResult
    freshness: str
    active_policy_matches: bool
    can_certify_current_schedule: bool = False

def policy(db, actor, id):
    row = services.one(db,"SELECT * FROM railplan.scoring_policies WHERE id=:id AND operator_id=:op AND definition IS NOT NULL",
                       id=id, op=actor["operator_id"])
    if not row: raise HTTPException(404,"Scoring policy not found")
    return dict(row)

def scoped_conflict(db, actor, id):
    c = services.one(db,"SELECT c.*,a.window_id FROM railplan.conflicts c JOIN railplan.analysis_runs a ON a.id=c.analysis_run_id WHERE c.id=:id",id=id)
    if not c: raise HTTPException(404,"Conflict not found")
    repo.window(db,c["window_id"],actor)
    return c

def snapshot(db, actor, id):
    # Share-lock prevents a source mutation from committing during this capture.
    revision = db.execute(text("SELECT revision FROM railplan.scoring_source_revision WHERE id=1 FOR SHARE")).scalar_one()
    c = scoped_conflict(db,actor,id)
    value = {"source_revision":revision, "conflict":repo.document(db,"conflicts",id),
             "rule":repo.document(db,"rule_definitions",c["rule_id"]),
             "analysis":repo.document(db,"analysis_runs",c["analysis_run_id"])}
    # Completed engine runs keep their recorded rule authority/severity/blocking.
    frozen = value["analysis"].get("rule_snapshot")
    if isinstance(frozen, list):
        value["rule"] = next((rule for rule in frozen
            if str(rule.get("id")) == str(c["rule_id"])), value["rule"])
    value["requests"] = repo.documents(db,"""SELECT to_jsonb(r)-'requested_period' FROM railplan.maintenance_requests r
      JOIN railplan.conflict_requests cr ON cr.request_id=r.id WHERE cr.conflict_id=:id ORDER BY r.id""",id=id)
    for r in value["requests"]: repo.request(db,r["id"],actor)
    for name in ("teams","engineers","equipment","sectors","isolations"):
        value[name] = repo.documents(db,f"SELECT to_jsonb(r) FROM railplan.conflict_{name} r WHERE conflict_id=:id ORDER BY id",id=id)
    value["scenario"] = None; value["assignments"] = []
    value["allocations"] = []
    sid = value["analysis"]["scenario_id"]
    if sid:
        s = repo.scenario(db,sid,actor)
        value["scenario"] = repo.document(db,"scenarios",sid)
        value["assignments"] = repo.documents(db,"""SELECT to_jsonb(a)-'period' FROM railplan.scenario_assignments a
          JOIN railplan.conflict_requests cr ON cr.request_id=a.request_id
          WHERE a.scenario_id=:s AND cr.conflict_id=:id ORDER BY a.request_id""",s=sid,id=id)
        versions = {r["id"]:r["version"] for r in value["requests"]}
        if any(a["request_version"] != versions[a["request_id"]] for a in value["assignments"]):
            raise HTTPException(409,"Scenario assignments use stale request versions; refresh the scenario first")
    for kind, table, column in (("engineer","engineers","engineer_id"),("asset","equipment","asset_id")):
        if sid:
            sql=f"""SELECT a.request_id,x.{column} AS resource_id FROM railplan.scenario_{table} x
              JOIN railplan.scenario_assignments a ON a.id=x.assignment_id
              JOIN railplan.conflict_requests cr ON cr.request_id=a.request_id
              WHERE cr.conflict_id=:id AND a.scenario_id=:sid ORDER BY a.request_id,x.{column}"""
        else:
            source="request_engineers" if kind=="engineer" else "request_equipment_assets"
            sql=f"""SELECT x.request_id,x.{column} AS resource_id FROM railplan.{source} x
              JOIN railplan.conflict_requests cr ON cr.request_id=x.request_id
              WHERE cr.conflict_id=:id ORDER BY x.request_id,x.{column}"""
        value["allocations"] += [{**r,"kind":kind} for r in repo.rows(db,sql,id=id,sid=sid)]
    # Normalize UUIDs to the same representation as to_jsonb documents.
    value["allocations"] = json.loads(canonical(value["allocations"]))
    return value

def score_document(db, actor, id):
    row = services.one(db,"SELECT * FROM railplan.conflict_scores WHERE id=:id",id=id)
    if not row: raise HTTPException(404,"Score not found")
    scoped_conflict(db,actor,row["conflict_id"])
    value = repo.document(db,"conflict_scores",id)
    current = db.execute(text("SELECT revision FROM railplan.scoring_source_revision WHERE id=1")).scalar_one()
    active = db.execute(text("SELECT policy_id FROM railplan.scoring_policy_activations WHERE operator_id=:op AND ends_at IS NULL"),{"op":actor["operator_id"]}).scalar_one_or_none()
    value.update(freshness="fresh" if current == row["source_revision"] and row["engine_version"] == ENGINE_VERSION else "stale",
                 active_policy_matches=active == row["policy_id"], can_certify_current_schedule=False)
    return value

@router.get("/scoring-policies", response_model=Page[Entity])
def list_policies(db:DB, actor:Actor, limit:Limit=50, offset:Offset=0):
    return repo.page(db,"""SELECT p.*,EXISTS(SELECT 1 FROM railplan.scoring_policy_activations a
      WHERE a.policy_id=p.id AND a.ends_at IS NULL) AS active FROM railplan.scoring_policies p
      WHERE operator_id=:op AND definition IS NOT NULL ORDER BY p.created_at DESC,p.id""",{"op":actor["operator_id"]},limit,offset)

@router.get("/scoring-policies/{policy_id}", response_model=Entity)
def get_policy(policy_id:UUID, db:DB, actor:Actor):
    policy(db,actor,policy_id)
    return repo.document(db,"scoring_policies",policy_id)

@router.post("/scoring-policies", response_model=Entity, status_code=201)
def create_policy(payload:PolicyCreate, db:DB, actor:Actor):
    role(actor,"administrator"); gate(db,actor)
    definition = payload.model_dump(mode="json")
    id = db.execute(text("""INSERT INTO railplan.scoring_policies(code,version,weights,is_validated,operator_id,definition)
      VALUES(:code,:version,CAST(:weights AS jsonb),false,:op,CAST(:definition AS jsonb)) RETURNING id"""),
      {"code":payload.code,"version":payload.version,"weights":canonical(definition["weights"]),
       "op":actor["operator_id"],"definition":canonical(definition)}).scalar_one()
    repo.event(db,actor,"scoring_policy_created","scoring_policy",id,"Created immutable unvalidated scoring policy")
    return repo.document(db,"scoring_policies",id)

@router.post("/scoring-policies/{policy_id}/activate", response_model=Entity)
def activate_policy(policy_id:UUID, db:DB, actor:Actor):
    role(actor,"administrator"); gate(db,actor); policy(db,actor,policy_id)
    current = services.one(db,"SELECT * FROM railplan.scoring_policy_activations WHERE operator_id=:op AND ends_at IS NULL",op=actor["operator_id"])
    if current and current["policy_id"] == policy_id: return dict(current)
    at = db.execute(text("SELECT clock_timestamp()")).scalar_one()
    db.execute(text("UPDATE railplan.scoring_policy_activations SET ends_at=:at WHERE operator_id=:op AND ends_at IS NULL"),{"at":at,"op":actor["operator_id"]})
    id = db.execute(text("""INSERT INTO railplan.scoring_policy_activations(operator_id,policy_id,activated_by,starts_at)
      VALUES(:op,:p,:u,:at) RETURNING id"""),{"op":actor["operator_id"],"p":policy_id,"u":actor["id"],"at":at}).scalar_one()
    repo.event(db,actor,"scoring_policy_activated","scoring_policy",policy_id,"Activated prototype scoring policy; operational approval remains disabled")
    return repo.document(db,"scoring_policy_activations",id)

@router.get("/conflicts/{conflict_id}/scoring-context", response_model=Entity)
def scoring_context(conflict_id:UUID, db:DB, actor:Actor):
    value = snapshot(db,actor,conflict_id)
    return {"id":conflict_id,"version":value["conflict"]["version"],"input_fingerprint":fingerprint(value),
            "source_revision":value["source_revision"],"analysis_freshness":"unknown",
            "can_recalculate":bool(actor["roles"] & {"administrator","safety_reviewer"})}

@router.post("/conflicts/{conflict_id}/scores", response_model=ScoreOut)
def calculate(conflict_id:UUID, payload:ScoreCreate, db:DB, actor:Actor):
    role(actor,"administrator","safety_reviewer"); gate(db,actor)
    scoped_conflict(db,actor,conflict_id)
    p = policy(db,actor,payload.policy_id)
    request_hash = fingerprint({"conflict_id":str(conflict_id),**payload.model_dump(mode="json",exclude={"idempotency_key"})})
    old = services.one(db,"SELECT * FROM railplan.score_idempotency_keys WHERE operator_id=:op AND key=:key",op=actor["operator_id"],key=payload.idempotency_key)
    if old:
        if old["request_fingerprint"] != request_hash: raise HTTPException(409,"Idempotency key was used for a different scoring request")
        return score_document(db,actor,old["score_id"])
    inputs = snapshot(db,actor,conflict_id)
    repo.version(inputs["conflict"],payload.expected_conflict_version)
    input_hash = fingerprint(inputs)
    if input_hash != payload.expected_input_fingerprint:
        raise HTTPException(409,"Scoring inputs changed; reload scoring-context before recalculating")
    definition = PolicyCreate.model_validate(p["definition"])
    policy_hash = fingerprint(p["definition"])
    result = evaluate(inputs,definition).model_dump(mode="json")
    id = db.execute(text("""INSERT INTO railplan.conflict_scores(conflict_id,policy_id,created_by,source_revision,
      input_fingerprint,policy_fingerprint,engine_version,input_snapshot,policy_snapshot,result)
      VALUES(:c,:p,:u,:rev,:ih,:ph,:engine,CAST(:inputs AS jsonb),CAST(:policy AS jsonb),CAST(:result AS jsonb))
      ON CONFLICT(conflict_id,policy_id,input_fingerprint,policy_fingerprint,engine_version) DO NOTHING RETURNING id"""),
      {"c":conflict_id,"p":payload.policy_id,"u":actor["id"],"rev":inputs["source_revision"],"ih":input_hash,
       "ph":policy_hash,"engine":ENGINE_VERSION,"inputs":canonical(inputs),"policy":canonical(p["definition"]),"result":canonical(result)}).scalar_one_or_none()
    if id is None:
        id = db.execute(text("""SELECT id FROM railplan.conflict_scores WHERE conflict_id=:c AND policy_id=:p
           AND input_fingerprint=:ih AND policy_fingerprint=:ph AND engine_version=:e"""),
           {"c":conflict_id,"p":payload.policy_id,"ih":input_hash,"ph":policy_hash,"e":ENGINE_VERSION}).scalar_one()
    else:
        repo.event(db,actor,"conflict_scored","conflict",conflict_id,"Recorded deterministic partial score with immutable evidence")
    db.execute(text("INSERT INTO railplan.score_idempotency_keys(operator_id,key,request_fingerprint,score_id) VALUES(:op,:key,:h,:s)"),
               {"op":actor["operator_id"],"key":payload.idempotency_key,"h":request_hash,"s":id})
    return score_document(db,actor,id)

@router.get("/conflicts/{conflict_id}/scores", response_model=Page[ScoreOut])
def history(conflict_id:UUID, db:DB, actor:Actor, limit:Limit=50, offset:Offset=0):
    scoped_conflict(db,actor,conflict_id)
    page = repo.page(db,"SELECT * FROM railplan.conflict_scores WHERE conflict_id=:id ORDER BY created_at DESC,id DESC",{"id":conflict_id},limit,offset)
    page["items"] = [score_document(db,actor,r["id"]) for r in page["items"]]
    return page

@router.get("/conflicts/{conflict_id}/scores/latest", response_model=ScoreOut | None)
def latest(conflict_id:UUID, db:DB, actor:Actor):
    scoped_conflict(db,actor,conflict_id)
    id = db.execute(text("SELECT id FROM railplan.conflict_scores WHERE conflict_id=:id ORDER BY created_at DESC,id DESC LIMIT 1"),{"id":conflict_id}).scalar_one_or_none()
    return score_document(db,actor,id) if id else None

@router.get("/conflict-scores/{score_id}", response_model=ScoreOut)
def get_score(score_id:UUID, db:DB, actor:Actor):
    return score_document(db,actor,score_id)
