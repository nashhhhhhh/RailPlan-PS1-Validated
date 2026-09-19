"""HTTP persistence metadata stays outside pure solver and CLI contracts."""
from datetime import datetime
from typing import Any, Annotated, Literal
from uuid import UUID
from pydantic import BaseModel, Field, model_validator
from .contracts import OptimiseInput, OptimiseResult

class SavedOptimiseInput(OptimiseInput):
    baseline_run_id: Annotated[UUID,Field(strict=False)] | None = None
    idempotency_key: str | None = Field(default=None,min_length=1,max_length=128,pattern=r'^\S+$')

    @model_validator(mode='after')
    def unambiguous_baseline(self):
        if self.baseline_run_id is not None and self.baseline_placements:
            raise ValueError('Use baseline_run_id or baseline_placements, not both')
        return self

class SavedOptimiseResult(OptimiseResult):
    run_id: UUID
    created: bool
    reused: bool
    created_at: datetime
    terminal_outcome: str
    input_fingerprint: str

class OptimisationPage(BaseModel):
    items: list[dict[str,Any]]
    total: int
    limit: int
    offset: int

class OptimisationDetail(BaseModel):
    run: dict[str,Any]
    result: OptimiseResult
    validation: dict[str,Any] | None
    diagnostics: list[dict[str,Any]]
    contract_results: list[dict[str,Any]]

class OptimisationArtifacts(BaseModel):
    run_id: UUID
    files: dict[str,str]
    physical_validation_complete: bool
    judge_validation: str = 'not_run'
    score_verification: str = 'internal_only'

JobStatus = Literal['QUEUED','RUNNING','SUCCEEDED','FAILED','CANCELLED']

class OptimisationJob(BaseModel):
    id: UUID
    instance_id: UUID
    operator_id: UUID
    created_by: UUID
    scenario: Literal['A','B','C']
    status: JobStatus
    progress: int = Field(ge=0,le=100)
    stage: str
    cancel_requested: bool
    run_id: UUID | None = None
    input_fingerprint: str
    solver_seed: int
    time_limit_seconds: float
    deterministic_time_limit: float
    option_snapshot: dict[str,Any]
    validator_version: str
    policy_version: str
    solver_status: str | None = None
    objective_components: dict[str,Any] | None = None
    best_objective: str | None = None
    best_bound: str | None = None
    validation_result: dict[str,Any] | None = None
    diagnostics: list[dict[str,Any]] = Field(default_factory=list)
    artifact_eligible: bool = False
    diagnostic: dict[str,Any] | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime

class OptimisationJobAccepted(BaseModel):
    job: OptimisationJob
    created: bool
    reused: bool
