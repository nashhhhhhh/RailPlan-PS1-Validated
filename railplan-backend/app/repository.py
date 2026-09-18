"""SQL fragments are developer constants; all external values are bound."""
from sqlalchemy import text
from fastapi import HTTPException
from app import services

def rows(db,sql,**params):
    return [dict(x) for x in db.execute(text(sql),params).mappings()]

def documents(db,sql,**params):
    return list(db.execute(text(sql),params).scalars())

def page(db,select,params,limit,offset):
    # select must include a stable ORDER BY and only developer-authored fragments.
    items=documents(db,"SELECT to_jsonb(q) FROM ("+select+") q LIMIT :limit OFFSET :offset",
                    **params,limit=limit,offset=offset)
    total=db.execute(text("SELECT count(*) FROM ("+select+") q"),params).scalar_one()
    return dict(items=items,total=total,limit=limit,offset=offset)

WINDOW_SCOPE="""w.line_id IN (SELECT l.id FROM railplan.lines l
 JOIN railplan.networks n ON n.id=l.network_id WHERE n.operator_id=:operator)"""

def window(db,id,actor):
    value=services.one(db,"SELECT w.* FROM railplan.engineering_windows w WHERE w.id=:id AND "+WINDOW_SCOPE,
                       id=id,operator=actor["operator_id"])
    if not value: raise HTTPException(404,"Engineering window not found")
    return dict(value)

def request(db,id,actor,lock=False):
    value=services.one(db,"""SELECT r.* FROM railplan.maintenance_requests r
     JOIN railplan.departments d ON d.id=r.department_id
     WHERE r.id=:id AND d.operator_id=:operator"""+(" FOR UPDATE OF r" if lock else ""),
     id=id,operator=actor["operator_id"])
    if not value: raise HTTPException(404,"Maintenance request not found")
    return dict(value)

def scenario(db,id,actor,lock=False):
    value=services.one(db,"""SELECT s.*,o.window_id FROM railplan.scenarios s
      JOIN railplan.optimisation_runs o ON o.id=s.run_id
      JOIN railplan.engineering_windows w ON w.id=o.window_id
      WHERE s.id=:id AND """+WINDOW_SCOPE+(" FOR UPDATE OF s" if lock else ""),
      id=id,operator=actor["operator_id"])
    if not value: raise HTTPException(404,"Scenario not found")
    return dict(value)

def document(db,table,id):
    # table is a fixed internal argument, never a path/query parameter.
    return db.execute(text(f"SELECT to_jsonb(r) FROM railplan.{table} r WHERE id=:id"),{"id":id}).scalar_one()

def version(record,expected):
    if record["version"]!=expected: raise HTTPException(409,"Stale version; reload before editing")

def event(db,actor,kind,entity,id,message):
    services.put(db,"activity_events",actor_id=actor["id"],event_type=kind,entity_type=entity,entity_id=id,message=message)

def latest_analysis(db,window_id,scenario_id):
    result=services.one(db,"""SELECT * FROM railplan.analysis_runs WHERE window_id=:w
      AND scenario_id IS NOT DISTINCT FROM CAST(:s AS uuid)
      ORDER BY created_at DESC,id DESC LIMIT 1""",w=window_id,s=scenario_id)
    if not result:return None
    value=dict(result)
    # Snapshot formats from v0.1 cannot certify freshness. Missing != fresh.
    return {"id":value["id"],"status":value["status"],"created_at":value["created_at"],
            "completed_at":value["completed_at"],"freshness":"unknown",
            "can_certify_current_schedule":False}

def active_locks(db,request_id,scenario_id=None):
    return rows(db,"""SELECT l.*,ARRAY(SELECT field FROM railplan.lock_fields f WHERE f.lock_id=l.id) AS fields
      FROM railplan.request_locks l WHERE l.request_id=:r AND l.released_at IS NULL
      AND (l.expires_at IS NULL OR l.expires_at>now())
      AND (l.scenario_id IS NULL OR l.scenario_id=CAST(:s AS uuid))""",r=request_id,s=scenario_id)
