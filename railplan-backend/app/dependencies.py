import os
from typing import Annotated
from uuid import UUID
from fastapi import Depends, Header, HTTPException, Request, Query
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.database import session
from app import services

DB=Annotated[Session,Depends(session,scope="function")]
Limit=Annotated[int,Query(ge=1,le=200)]
Offset=Annotated[int,Query(ge=0,le=100000)]

def identity(request:Request,db:DB,x_demo_user_id:Annotated[UUID|None,Header()]=None):
    if os.environ.get("RAILPLAN_ENV","development")!="development" or os.environ.get("RAILPLAN_DEMO_AUTH")!="1":
        raise HTTPException(503,"Verified authentication is not configured; local demo identity is disabled")
    if x_demo_user_id is None: raise HTTPException(401,"X-Demo-User-Id is required")
    actor=services.one(db,"""SELECT u.*,d.operator_id FROM railplan.users u
      JOIN railplan.departments d ON d.id=u.department_id WHERE u.id=:id AND u.active""",id=x_demo_user_id)
    if actor is None: raise HTTPException(401,"Unknown or inactive user")
    actor=dict(actor)
    actor["roles"]=set(db.execute(text("""SELECT r.code FROM railplan.user_roles ur
      JOIN railplan.roles r ON r.id=ur.role_id WHERE ur.user_id=:id"""),{"id":actor["id"]}).scalars())
    if not actor["roles"]: raise HTTPException(403,"No application role assigned")
    db.execute(text("""SELECT set_config('railplan.actor_id',:a,true),
       set_config('railplan.source','ui',true),set_config('railplan.correlation_id',:c,true)"""),
       {"a":str(actor["id"]),"c":request.state.correlation_id})
    return actor

Actor=Annotated[dict,Depends(identity)]
def role(actor,*allowed):
    if not actor["roles"].intersection(allowed): raise HTTPException(403,"Role does not permit this operation")
def writer(actor): role(actor,"planner","engineering_supervisor","administrator")
