"""Dedicated PS1 terminal history mappings; SQL migration owns sealing triggers."""
from datetime import datetime, date
from decimal import Decimal
from typing import Any
from uuid import UUID
from sqlalchemy import Text, DateTime, Date, Integer, BigInteger, Boolean, Numeric, Float, ForeignKey, ForeignKeyConstraint, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.models import Base

class PS1OptimisationRuns(Base):
    __tablename__='ps1_optimisation_runs'
    __table_args__=(UniqueConstraint('id','instance_id','operator_id'),UniqueConstraint('id','instance_id','operator_id','input_fingerprint'),
        ForeignKeyConstraint(['instance_id','operator_id'],['railplan.ps1_instances.id','railplan.ps1_instances.operator_id']),
        ForeignKeyConstraint(['baseline_run_id','instance_id','operator_id'],['railplan.ps1_optimisation_runs.id','railplan.ps1_optimisation_runs.instance_id','railplan.ps1_optimisation_runs.operator_id']),{'schema':'railplan'})
    id:Mapped[UUID]=mapped_column(PGUUID,primary_key=True,server_default=text('gen_random_uuid()'))
    instance_id:Mapped[UUID]=mapped_column(PGUUID)
    operator_id:Mapped[UUID]=mapped_column(ForeignKey('railplan.operators.id'))
    created_by:Mapped[UUID]=mapped_column(ForeignKey('railplan.users.id'))
    baseline_run_id:Mapped[UUID|None]=mapped_column(PGUUID)
    scenario:Mapped[str]=mapped_column(Text)
    solver_status:Mapped[str]=mapped_column(Text)
    terminal_outcome:Mapped[str]=mapped_column(Text)
    optimiser_version:Mapped[str]=mapped_column(Text)
    validator_version:Mapped[str]=mapped_column(Text)
    policy_version:Mapped[str]=mapped_column(Text)
    dataset_fingerprint:Mapped[str]=mapped_column(Text)
    input_fingerprint:Mapped[str]=mapped_column(Text)
    request_snapshot:Mapped[dict[str,Any]]=mapped_column(JSONB)
    solver_configuration:Mapped[dict[str,Any]]=mapped_column(JSONB)
    result_snapshot:Mapped[dict[str,Any]]=mapped_column(JSONB)
    validation_snapshot:Mapped[dict[str,Any]|None]=mapped_column(JSONB)
    diagnostics:Mapped[list]=mapped_column(JSONB)
    primary_optimal:Mapped[bool]=mapped_column(Boolean)
    lexicographic_complete:Mapped[bool]=mapped_column(Boolean)
    physical_validation_complete:Mapped[bool]=mapped_column(Boolean)
    publishable:Mapped[bool]=mapped_column(Boolean)
    objective_score:Mapped[Decimal|None]=mapped_column(Numeric)
    primary_objective_bound:Mapped[Decimal|None]=mapped_column(Numeric)
    primary_objective_gap:Mapped[Decimal|None]=mapped_column(Numeric)
    solve_duration_seconds:Mapped[float]=mapped_column(Float)
    started_at:Mapped[datetime]=mapped_column(DateTime(timezone=True))
    completed_at:Mapped[datetime]=mapped_column(DateTime(timezone=True))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=text('clock_timestamp()'))
    accepted_csvs:Mapped[dict[str,str]|None]=mapped_column(JSONB)
    schedule_snapshot:Mapped[dict[str,Any]]=mapped_column(JSONB)
    creation_txid:Mapped[int]=mapped_column(BigInteger,server_default=text('txid_current()'))

class RunScope:
    run_id:Mapped[UUID]=mapped_column(PGUUID,primary_key=True)
    instance_id:Mapped[UUID]=mapped_column(PGUUID)
    operator_id:Mapped[UUID]=mapped_column(PGUUID)

def parent_fk():
    return ForeignKeyConstraint(['run_id','instance_id','operator_id'],['railplan.ps1_optimisation_runs.id','railplan.ps1_optimisation_runs.instance_id','railplan.ps1_optimisation_runs.operator_id'])

class PS1OptimisationAccesses(RunScope,Base):
    __tablename__='ps1_optimisation_accesses'
    __table_args__=(parent_fk(),UniqueConstraint('run_id','activity_id','week'),{'schema':'railplan'})
    activity_id:Mapped[str]=mapped_column(Text,primary_key=True)
    access_seq:Mapped[int]=mapped_column(Integer,primary_key=True)
    week:Mapped[int]=mapped_column(Integer)
    physical_night:Mapped[int]=mapped_column(Integer)
    access_night:Mapped[int]=mapped_column(Integer)
    eclo:Mapped[int]=mapped_column(Integer)
    locked:Mapped[bool]=mapped_column(Boolean)
    baseline_week:Mapped[int|None]=mapped_column(Integer)
    baseline_physical_night:Mapped[int|None]=mapped_column(Integer)

class PS1OptimisationOccupancies(RunScope,Base):
    __tablename__='ps1_optimisation_occupancies'
    __table_args__=(parent_fk(),ForeignKeyConstraint(['run_id','activity_id','week'],['railplan.ps1_optimisation_accesses.run_id','railplan.ps1_optimisation_accesses.activity_id','railplan.ps1_optimisation_accesses.week']),{'schema':'railplan'})
    activity_id:Mapped[str]=mapped_column(Text,primary_key=True)
    week:Mapped[int]=mapped_column(Integer,primary_key=True)
    location_id:Mapped[str]=mapped_column(Text,primary_key=True)
    co_share_group:Mapped[str]=mapped_column(Text)

class PS1OptimisationContractResults(RunScope,Base):
    __tablename__='ps1_optimisation_contract_results'
    __table_args__=(parent_fk(),{'schema':'railplan'})
    contract_number:Mapped[str]=mapped_column(Text,primary_key=True)
    simulated_completion_date:Mapped[date]=mapped_column(Date)
    overrun_days:Mapped[int]=mapped_column(Integer)
    weighted_overrun:Mapped[Decimal|None]=mapped_column(Numeric)

class PS1OptimisationKeys(Base):
    __tablename__='ps1_optimisation_keys'
    __table_args__=(ForeignKeyConstraint(['run_id','instance_id','operator_id','input_fingerprint'],['railplan.ps1_optimisation_runs.id','railplan.ps1_optimisation_runs.instance_id','railplan.ps1_optimisation_runs.operator_id','railplan.ps1_optimisation_runs.input_fingerprint']),{'schema':'railplan'})
    operator_id:Mapped[UUID]=mapped_column(PGUUID,primary_key=True)
    instance_id:Mapped[UUID]=mapped_column(PGUUID,primary_key=True)
    idempotency_key:Mapped[str]=mapped_column(Text,primary_key=True)
    input_fingerprint:Mapped[str]=mapped_column(Text)
    run_id:Mapped[UUID]=mapped_column(PGUUID)

class PS1OptimisationJobs(Base):
    __tablename__='ps1_optimisation_jobs'
    __table_args__=(ForeignKeyConstraint(['instance_id','operator_id'],['railplan.ps1_instances.id','railplan.ps1_instances.operator_id']),
        ForeignKeyConstraint(['run_id','instance_id','operator_id'],['railplan.ps1_optimisation_runs.id','railplan.ps1_optimisation_runs.instance_id','railplan.ps1_optimisation_runs.operator_id']),
        {'schema':'railplan'})
    id:Mapped[UUID]=mapped_column(PGUUID,primary_key=True,server_default=text('gen_random_uuid()'))
    instance_id:Mapped[UUID]=mapped_column(PGUUID)
    operator_id:Mapped[UUID]=mapped_column(ForeignKey('railplan.operators.id'))
    created_by:Mapped[UUID]=mapped_column(ForeignKey('railplan.users.id'))
    scenario:Mapped[str]=mapped_column(Text)
    status:Mapped[str]=mapped_column(Text)
    progress:Mapped[int]=mapped_column(Integer,server_default=text('0'))
    stage:Mapped[str]=mapped_column(Text,server_default=text("'queued'"))
    idempotency_key:Mapped[str|None]=mapped_column(Text)
    input_fingerprint:Mapped[str]=mapped_column(Text)
    request_snapshot:Mapped[dict[str,Any]]=mapped_column(JSONB)
    cancel_requested:Mapped[bool]=mapped_column(Boolean,server_default=text('false'))
    run_id:Mapped[UUID|None]=mapped_column(PGUUID)
    diagnostic:Mapped[dict[str,Any]|None]=mapped_column(JSONB)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=text('clock_timestamp()'))
    started_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    completed_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=text('clock_timestamp()'))
