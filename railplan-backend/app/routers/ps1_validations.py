"""PS1-only validation endpoints; stateless preview does not resolve identity."""
from uuid import UUID
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from app.dependencies import Actor, DB, Limit, Offset, role
from app import repository
from app.ps1 import parse_instance, InstanceError
from app.ps1_validation.contracts import PreviewInput, SubmissionInput, ValidationReport
from app.ps1_validation.service import validate
from app.ps1_validation.persistence import persist, get_run, get_instance

router=APIRouter(prefix='/api/ps1',tags=['PS1 submission validation'])

class SavedValidation(BaseModel):
    id: UUID
    created: bool
    report: ValidationReport

@router.post('/validate',response_model=ValidationReport)
def preview(payload:PreviewInput):
    try: dataset=parse_instance(payload.instance_files)
    except (InstanceError,UnicodeEncodeError) as exc: raise HTTPException(422,str(exc))
    return validate(dataset,payload.files,payload.scenario)

@router.post('/instances/{instance_id}/validations',response_model=SavedValidation)
def create(instance_id:UUID,payload:SubmissionInput,db:DB,actor:Actor):
    role(actor,'planner','administrator')
    return persist(db,actor,instance_id,payload)

@router.get('/instances/{instance_id}/validations')
def history(instance_id:UUID,db:DB,actor:Actor,limit:Limit=50,offset:Offset=0):
    get_instance(db,actor,instance_id)
    return repository.page(db,'''SELECT id,instance_id,scenario,validator_version,created_at,
        result_snapshot->'feasible' AS feasible FROM railplan.ps1_validation_runs
        WHERE instance_id=:id AND operator_id=:op ORDER BY created_at DESC,id''',
        {'id':instance_id,'op':actor['operator_id']},limit,offset)

@router.get('/validations/{validation_id}')
def detail(validation_id:UUID,db:DB,actor:Actor):
    return get_run(db,actor,validation_id)

@router.get('/validations/{validation_id}/violations')
def violations(validation_id:UUID,db:DB,actor:Actor,limit:Limit=50,offset:Offset=0,rule_code:str|None=Query(default=None,max_length=64)):
    get_run(db,actor,validation_id)
    return repository.page(db,'''SELECT ordinal,rule_code,evidence_snapshot FROM railplan.ps1_validation_violations
        WHERE validation_id=:id AND operator_id=:op AND (CAST(:rule AS text) IS NULL OR rule_code=:rule)
        ORDER BY ordinal''',{'id':validation_id,'op':actor['operator_id'],'rule':rule_code},limit,offset)
