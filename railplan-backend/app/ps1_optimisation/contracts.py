from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field
from app.ps1_validation.contracts import ValidationReport

VERSION = 'ps1-optimiser/1.0.0'

class Placement(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    activity_id: str = Field(min_length=1, max_length=128)
    access_seq: int = Field(ge=1, le=520)
    week: int = Field(ge=1, le=520)
    physical_night: int = Field(ge=1, le=7)
    access_night: int | None = Field(default=None, ge=1, le=1000)

class OptimiseInput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    time_limit_seconds: float = Field(default=20, ge=0.1, le=120)
    deterministic_time_limit: float = Field(default=10, ge=0.001, le=60)
    random_seed: int = Field(default=0, ge=0, le=2147483647)
    physical_nights_per_week: int = Field(default=7, ge=1, le=7)
    locked_placements: list[Placement] = Field(default_factory=list, max_length=2000)
    baseline_placements: list[Placement] = Field(default_factory=list, max_length=2000)

class OptimiseResult(BaseModel):
    scenario: Literal['A'] = 'A'
    optimiser_version: str = VERSION
    solver_status: str
    publishable: bool = False
    primary_optimal: bool = False
    lexicographic_complete: bool = False
    solve_time_seconds: float
    objective_components: dict[str, Any] | None = None
    submission_files: dict[str, str] | None = None
    physical_nights: list[Placement] = Field(default_factory=list)
    physical_validation_complete: bool = False
    validation_report: ValidationReport | None = None
    completion_changes: list[dict[str, Any]] = Field(default_factory=list)
    diagnostics: list[dict[str, Any]] = Field(default_factory=list)
    stages: list[dict[str, Any]] = Field(default_factory=list)
    settings: dict[str, Any]
    failed_candidate: dict[str, Any] | None = None
    judge_validation: Literal['not_run'] = 'not_run'
    score_verification: Literal['internal_only'] = 'internal_only'
