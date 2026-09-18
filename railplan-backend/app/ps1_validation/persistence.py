"""Scoped append-only persistence. Caller owns the transaction boundary."""
import json
from fastapi import HTTPException
from sqlalchemy import text
from app import repository
from .contracts import VERSION
from .submission import fingerprint
from .service import validate

def get_run(db, actor, validation_id):
    row=db.execute(text('SELECT * FROM railplan.ps1_validation_runs WHERE id=:id AND operator_id=:op'),
                   {'id':validation_id,'op':actor['operator_id']}).mappings().one_or_none()
    if row is None: raise HTTPException(404,'PS1 validation not found')
    return dict(row)

def get_instance(db, actor, instance_id):
    row=db.execute(text('SELECT * FROM railplan.ps1_instances WHERE id=:id AND operator_id=:op'),
                   {'id':instance_id,'op':actor['operator_id']}).mappings().one_or_none()
    if row is None: raise HTTPException(404,'PS1 instance not found')
    return dict(row)

def persist(db, actor, instance_id, payload):
    instance=get_instance(db,actor,instance_id)
    digest=fingerprint({'instance_id':str(instance_id),'scenario':payload.scenario,'files':payload.files,'version':VERSION})
    params={'op':actor['operator_id'],'key':payload.idempotency_key,'digest':digest}
    # Serialize keys before content locks, consistently across concurrent requests.
    if payload.idempotency_key:
        db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:lock,0))'),
                   {'lock':f"ps1-key/{actor['operator_id']}/{payload.idempotency_key}"})
        existing=db.execute(text('SELECT * FROM railplan.ps1_validation_keys WHERE operator_id=:op AND idempotency_key=:key'),params).mappings().one_or_none()
        if existing:
            if existing['request_fingerprint']!=digest: raise HTTPException(409,'Idempotency key was already used for different content')
            return {'id':existing['validation_id'],'created':False,'report':get_run(db,actor,existing['validation_id'])['result_snapshot']}
    db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:lock,0))'),{'lock':'ps1-content/'+digest})
    submission_hash=fingerprint({'scenario':payload.scenario,'files':payload.files})
    existing=db.execute(text('''SELECT id,result_snapshot FROM railplan.ps1_validation_runs
        WHERE instance_id=:instance AND operator_id=:op AND submission_fingerprint=:hash AND validator_version=:version'''),
        {'instance':instance_id,'op':actor['operator_id'],'hash':submission_hash,'version':VERSION}).mappings().one_or_none()
    created=existing is None
    if existing:
        validation_id, report=existing['id'],existing['result_snapshot']
    else:
        report=validate(instance['dataset'],payload.files,payload.scenario)
        validation_id=db.execute(text('''INSERT INTO railplan.ps1_validation_runs
            (instance_id,operator_id,created_by,scenario,dataset_fingerprint,submission_fingerprint,
             validator_version,source_files,policy_snapshot,result_snapshot)
            VALUES(:instance,:op,:creator,:scenario,:dataset,:hash,:version,CAST(:files AS jsonb),CAST(:policy AS jsonb),CAST(:result AS jsonb)) RETURNING id'''),
            {'instance':instance_id,'op':actor['operator_id'],'creator':actor['id'],'scenario':payload.scenario,
             'dataset':report['dataset_fingerprint'],'hash':submission_hash,'version':VERSION,'files':json.dumps(payload.files),
             'policy':json.dumps(report['rule_policy']),'result':json.dumps(report)}).scalar_one()
        rows=[{'id':validation_id,'op':actor['operator_id'],'ordinal':i,'rule':v['rule_code'],'value':json.dumps(v)}
              for i,v in enumerate(report['hard_violations'])]
        if rows:
            db.execute(text('''INSERT INTO railplan.ps1_validation_violations(validation_id,operator_id,ordinal,rule_code,evidence_snapshot)
                VALUES(:id,:op,:ordinal,:rule,CAST(:value AS jsonb))'''),rows)
        repository.event(db,actor,'ps1_validation_completed','ps1_validation',validation_id,
                         f"Internal provisional PS1 validation: {len(rows)} hard violations")
    if payload.idempotency_key:
        db.execute(text('''INSERT INTO railplan.ps1_validation_keys(operator_id,idempotency_key,request_fingerprint,validation_id)
            VALUES(:op,:key,:digest,:id)'''),{**params,'id':validation_id})
    return {'id':validation_id,'created':created,'report':report}
