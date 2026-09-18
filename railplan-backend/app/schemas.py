from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, AwareDatetime, model_validator

class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")

class EquipmentRequirement(Input):
    type_id: UUID
    quantity: int = Field(default=1,gt=0)

class SkillRequirement(Input):
    skill_id: UUID
    required_count: int = Field(default=1,gt=0)

class IsolationRequirement(Input):
    isolation_zone_id: UUID
    required_state: Literal["isolated","restored"]

class RequestCreate(Input):
    submit: bool = True
    window_id: UUID
    work_type_id: UUID
    title: str = Field(min_length=1,max_length=200)
    description: str = Field(default="",max_length=10000)
    requested_start: AwareDatetime
    requested_end: AwareDatetime
    earliest_start: AwareDatetime
    latest_finish: AwareDatetime
    min_duration_minutes: int = Field(gt=0)
    max_duration_minutes: int = Field(gt=0)
    priority: Literal["normal","high","urgent"] = "normal"
    sector_ids: list[UUID] = Field(min_length=1,max_length=100)
    team_ids: list[UUID] = Field(default_factory=list,max_length=100)
    engineer_ids: list[UUID] = Field(default_factory=list,max_length=200)
    workzone_ids: list[UUID] = Field(default_factory=list,max_length=100)
    equipment: list[EquipmentRequirement] = Field(default_factory=list,max_length=100)
    skills: list[SkillRequirement] = Field(default_factory=list,max_length=100)
    isolations: list[IsolationRequirement] = Field(default_factory=list,max_length=100)

    @model_validator(mode="after")
    def coherent(self):
        self.title=self.title.strip()
        if not self.title:
            raise ValueError("Title must not be blank")
        duration=(self.requested_end-self.requested_start).total_seconds()/60
        if not 0 < self.min_duration_minutes <= duration <= self.max_duration_minutes:
            raise ValueError("Duration must be positive and within min/max limits")
        if not self.earliest_start<=self.requested_start<self.requested_end<=self.latest_finish:
            raise ValueError("Requested interval must fit its flexibility window")
        for field in ("sector_ids","team_ids","engineer_ids","workzone_ids"):
            values=getattr(self,field)
            if len(values)!=len(set(values)):
                raise ValueError(f"Duplicate {field}")
        for field,key in (("equipment","type_id"),("skills","skill_id"),("isolations","isolation_zone_id")):
            values=[getattr(x,key) for x in getattr(self,field)]
            if len(values)!=len(set(values)):
                raise ValueError(f"Duplicate {field}")
        return self

class AnalysisCreate(Input):
    window_id: UUID
    scenario_id: UUID | None = None

class OptimisationCreate(Input):
    window_id: UUID
    objective_id: UUID
    parameters: dict = Field(default_factory=dict)

class LockCreate(Input):
    expected_version: int = Field(gt=0)
    scenario_id: UUID | None = None
    reason: str = Field(min_length=1,max_length=2000)
    fields: list[Literal["timing","team","engineers","equipment","sectors"]] = Field(default=["timing"],min_length=1,max_length=5)
    expires_at: AwareDatetime | None = None

class ApprovalSubmit(Input):
    workflow_id: UUID
    expected_version: int = Field(gt=0)

class ApprovalDecision(Input):
    stage_id: UUID
    decision: Literal["approved","rejected"]
    comment: str = Field(min_length=1,max_length=5000)
