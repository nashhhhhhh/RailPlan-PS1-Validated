"""Immutable instance versions; original CSVs and parsed records are retained."""
from datetime import datetime
from typing import Any
from uuid import UUID
from sqlalchemy import Text, DateTime, ForeignKey, Integer, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID,JSONB
from sqlalchemy.orm import Mapped,mapped_column
from app.models import Base

class PS1Instances(Base):
    __tablename__='ps1_instances'
    __table_args__={'schema':'railplan'}
    id:Mapped[UUID]=mapped_column(PGUUID,primary_key=True,server_default=text('gen_random_uuid()'))
    operator_id:Mapped[UUID]=mapped_column(ForeignKey('railplan.operators.id',ondelete='RESTRICT'))
    imported_by:Mapped[UUID]=mapped_column(ForeignKey('railplan.users.id',ondelete='RESTRICT'))
    name:Mapped[str]=mapped_column(Text)
    fingerprint:Mapped[str]=mapped_column(Text)
    format_version:Mapped[str]=mapped_column(Text)
    source_files:Mapped[dict[str,Any]]=mapped_column(JSONB)
    dataset:Mapped[dict[str,Any]]=mapped_column(JSONB)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=text('clock_timestamp()'))

class PS1ValidationRuns(Base):
    __tablename__='ps1_validation_runs'
    __table_args__={'schema':'railplan'}
    id:Mapped[UUID]=mapped_column(PGUUID,primary_key=True,server_default=text('gen_random_uuid()'))
    instance_id:Mapped[UUID]=mapped_column(ForeignKey('railplan.ps1_instances.id'))
    operator_id:Mapped[UUID]=mapped_column(ForeignKey('railplan.operators.id'))
    created_by:Mapped[UUID]=mapped_column(ForeignKey('railplan.users.id'))
    scenario:Mapped[str]=mapped_column(Text)
    dataset_fingerprint:Mapped[str]=mapped_column(Text)
    submission_fingerprint:Mapped[str]=mapped_column(Text)
    validator_version:Mapped[str]=mapped_column(Text)
    source_files:Mapped[dict[str,Any]]=mapped_column(JSONB)
    policy_snapshot:Mapped[dict[str,Any]]=mapped_column(JSONB)
    result_snapshot:Mapped[dict[str,Any]]=mapped_column(JSONB)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=text('clock_timestamp()'))

class PS1ValidationViolations(Base):
    __tablename__='ps1_validation_violations'
    __table_args__={'schema':'railplan'}
    id:Mapped[UUID]=mapped_column(PGUUID,primary_key=True,server_default=text('gen_random_uuid()'))
    validation_id:Mapped[UUID]=mapped_column(ForeignKey('railplan.ps1_validation_runs.id'))
    operator_id:Mapped[UUID]=mapped_column(ForeignKey('railplan.operators.id'))
    ordinal:Mapped[int]=mapped_column(Integer)
    rule_code:Mapped[str]=mapped_column(Text)
    evidence_snapshot:Mapped[dict[str,Any]]=mapped_column(JSONB)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=text('clock_timestamp()'))

class PS1ValidationKeys(Base):
    __tablename__='ps1_validation_keys'
    __table_args__={'schema':'railplan'}
    id:Mapped[UUID]=mapped_column(PGUUID,primary_key=True,server_default=text('gen_random_uuid()'))
    operator_id:Mapped[UUID]=mapped_column(ForeignKey('railplan.operators.id'))
    idempotency_key:Mapped[str]=mapped_column(Text)
    request_fingerprint:Mapped[str]=mapped_column(Text)
    validation_id:Mapped[UUID]=mapped_column(ForeignKey('railplan.ps1_validation_runs.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=text('clock_timestamp()'))
