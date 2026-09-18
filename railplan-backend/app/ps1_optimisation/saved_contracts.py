"""HTTP persistence metadata stays outside pure solver and CLI contracts."""
from datetime import datetime
from typing import Any, Annotated
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
