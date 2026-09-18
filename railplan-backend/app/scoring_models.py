"""SQLAlchemy projections of migration 0003; SQL owns constraints and triggers."""
from datetime import datetime
from typing import Any
from uuid import UUID
from sqlalchemy import Integer, BigInteger, Text, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.models import Base

class ScoringSourceRevision(Base):
    __tablename__ = "scoring_source_revision"
    __table_args__ = {"schema":"railplan"}
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    revision: Mapped[int] = mapped_column(BigInteger, server_default=text("1"))

class ScoringPolicyActivations(Base):
    __tablename__ = "scoring_policy_activations"
    __table_args__ = {"schema":"railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID, primary_key=True, server_default=text("gen_random_uuid()"))
    operator_id: Mapped[UUID] = mapped_column(ForeignKey("railplan.operators.id",ondelete="RESTRICT"))
    policy_id: Mapped[UUID] = mapped_column(ForeignKey("railplan.scoring_policies.id",ondelete="RESTRICT"))
    activated_by: Mapped[UUID] = mapped_column(ForeignKey("railplan.users.id",ondelete="RESTRICT"))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),server_default=text("clock_timestamp()"))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class ConflictScores(Base):
    __tablename__ = "conflict_scores"
    __table_args__ = {"schema":"railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID,primary_key=True,server_default=text("gen_random_uuid()"))
    conflict_id: Mapped[UUID] = mapped_column(ForeignKey("railplan.conflicts.id",ondelete="RESTRICT"))
    policy_id: Mapped[UUID] = mapped_column(ForeignKey("railplan.scoring_policies.id",ondelete="RESTRICT"))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("railplan.users.id",ondelete="RESTRICT"))
    source_revision: Mapped[int] = mapped_column(BigInteger)
    input_fingerprint: Mapped[str] = mapped_column(Text)
    policy_fingerprint: Mapped[str] = mapped_column(Text)
    engine_version: Mapped[str] = mapped_column(Text)
    input_snapshot: Mapped[dict[str,Any]] = mapped_column(JSONB)
    policy_snapshot: Mapped[dict[str,Any]] = mapped_column(JSONB)
    result: Mapped[dict[str,Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),server_default=text("clock_timestamp()"))

class ScoreIdempotencyKeys(Base):
    __tablename__ = "score_idempotency_keys"
    __table_args__ = {"schema":"railplan"}
    id: Mapped[UUID] = mapped_column(PGUUID,primary_key=True,server_default=text("gen_random_uuid()"))
    operator_id: Mapped[UUID] = mapped_column(ForeignKey("railplan.operators.id",ondelete="RESTRICT"))
    key: Mapped[str] = mapped_column(Text)
    request_fingerprint: Mapped[str] = mapped_column(Text)
    score_id: Mapped[UUID] = mapped_column(ForeignKey("railplan.conflict_scores.id",ondelete="RESTRICT"))
