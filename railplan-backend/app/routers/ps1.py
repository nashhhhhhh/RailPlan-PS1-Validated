"""Import/inspect the organiser's eight-file instance format."""
import json
from app import ps1_models
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from app.dependencies import Actor,DB,Limit,Offset,writer
from app import repository as repo
from app.ps1 import parse_instance,load_files,InstanceError

router=APIRouter(prefix="/api/ps1",tags=["PS1 hackathon datasets"])

class InstanceInput(BaseModel):
    model_config=ConfigDict(extra="forbid",str_strip_whitespace=False)
    name:str=Field(default="PS1 uploaded instance",min_length=1,max_length=120)
    files:dict[str,Annotated[str,Field(max_length=4_000_000)]]=Field(min_length=8,max_length=8)

def parsed(payload):
    if not payload.name.strip():raise HTTPException(422,"Instance name cannot be blank")
    try:return parse_instance(payload.files)
    except InstanceError as exc:raise HTTPException(422,str(exc))

@router.post("/preview")
def preview(payload:InstanceInput):
    # Stateless local validation permits use before PostgreSQL/auth setup.
    return parsed(payload)

@router.get("/example")
def example():
    files=load_files()
    return {"name":"Organiser PS1 public instance","files":files,"dataset":parse_instance(files)}

@router.post("/instances")
def import_instance(payload:InstanceInput,db:DB,actor:Actor):
    writer(actor);dataset=parsed(payload)
    params={"op":actor['operator_id'],"u":actor['id'],"name":payload.name.strip(),
      "hash":dataset['fingerprint'],"version":dataset['format_version'],
      "files":json.dumps(payload.files),"dataset":json.dumps(dataset)}
    id=db.execute(text("""INSERT INTO railplan.ps1_instances(operator_id,imported_by,name,fingerprint,format_version,source_files,dataset)
      VALUES(:op,:u,:name,:hash,:version,CAST(:files AS jsonb),CAST(:dataset AS jsonb))
      ON CONFLICT(operator_id,fingerprint,format_version) DO NOTHING RETURNING id"""),params).scalar_one_or_none()
    created=id is not None
    if id is None:
        id=db.execute(text("SELECT id FROM railplan.ps1_instances WHERE operator_id=:op AND fingerprint=:hash AND format_version=:version"),params).scalar_one()
    else:repo.event(db,actor,"ps1_instance_imported","ps1_instance",id,f"Imported {dataset['summary']['activities']} PS1 activities")
    return {"id":id,"created":created,"dataset":dataset}

@router.get("/instances")
def instances(db:DB,actor:Actor,limit:Limit=50,offset:Offset=0):
    return repo.page(db,"""SELECT id,name,fingerprint,format_version,created_at,dataset->'summary' AS summary
      FROM railplan.ps1_instances WHERE operator_id=:op ORDER BY created_at DESC,id""",{"op":actor['operator_id']},limit,offset)

@router.get("/instances/{instance_id}")
def instance(instance_id:UUID,db:DB,actor:Actor):
    row=db.execute(text("SELECT id,name,fingerprint,format_version,created_at,dataset FROM railplan.ps1_instances WHERE id=:id AND operator_id=:op"),
                   {"id":instance_id,"op":actor['operator_id']}).mappings().one_or_none()
    if row is None:raise HTTPException(404,"PS1 instance not found")
    return dict(row)
