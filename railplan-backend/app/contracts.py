"""Public response models and bounded mutation contracts."""
from datetime import datetime
from typing import Any, Generic, Literal, TypeVar
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, AwareDatetime, model_validator
from app.schemas import Input, RequestCreate,EquipmentRequirement,SkillRequirement,IsolationRequirement

T=TypeVar("T")
class Page(BaseModel,Generic[T]):
    items:list[T]
    limit:int
    offset:int
    total:int

class Entity(BaseModel):
    model_config=ConfigDict(extra="allow")
    id:UUID

class Named(Entity):
    name:str

class Capabilities(BaseModel):
    conflict_analysis_available:bool=True
    optimisation_available:bool=False
    copilot_available:bool=False
    operational_approval_available:bool=False

class RequestOut(Entity):
    request_code:str
    title:str
    description:str
    window_id:UUID
    requested_start:datetime
    requested_end:datetime
    version:int
    status_code:str
    priority:str

class AssignmentOut(Entity):
    scenario_id:UUID
    request_id:UUID
    starts_at:datetime
    ends_at:datetime
    original_start:datetime
    original_end:datetime
    feasible:bool
    reason:str

class ScenarioOut(Entity):
    name:str
    status:str
    version:int
    validation_status:str
    provenance:str

class Mutation(BaseModel):
    id:UUID
    status:str
    version:int|None=None
    validation_status:str|None=None

class ExpectedVersion(Input):
    expected_version:int=Field(gt=0)

class RequestPatch(ExpectedVersion):
    work_type_id:UUID|None=None
    sector_ids:list[UUID]|None=Field(default=None,min_length=1,max_length=100)
    team_ids:list[UUID]|None=Field(default=None,max_length=100)
    engineer_ids:list[UUID]|None=Field(default=None,max_length=200)
    workzone_ids:list[UUID]|None=Field(default=None,max_length=100)
    equipment:list[EquipmentRequirement]|None=Field(default=None,max_length=100)
    skills:list[SkillRequirement]|None=Field(default=None,max_length=100)
    isolations:list[IsolationRequirement]|None=Field(default=None,max_length=100)
    title:str|None=Field(default=None,min_length=1,max_length=200)
    description:str|None=Field(default=None,max_length=10000)
    priority:Literal["normal","high","urgent"]|None=None
    requested_start:AwareDatetime|None=None
    requested_end:AwareDatetime|None=None
    earliest_start:AwareDatetime|None=None
    latest_finish:AwareDatetime|None=None
    min_duration_minutes:int|None=Field(default=None,gt=0)
    max_duration_minutes:int|None=Field(default=None,gt=0)
    @model_validator(mode="after")
    def present(self):
        supplied=self.model_fields_set-{"expected_version"}
        if not supplied: raise ValueError("Supply at least one editable field")
        if any(getattr(self,f) is None for f in supplied): raise ValueError("Editable fields cannot be null")
        if self.title is not None:
            self.title=self.title.strip()
            if not self.title: raise ValueError("Title cannot be blank")
        for field in ("sector_ids","team_ids","engineer_ids","workzone_ids"):
            values=getattr(self,field)
            if values is not None and len(values)!=len(set(values)):raise ValueError("Duplicate "+field)
        for field,key in (("equipment","type_id"),("skills","skill_id"),("isolations","isolation_zone_id")):
            values=getattr(self,field)
            if values is not None:
                ids=[getattr(x,key) for x in values]
                if len(ids)!=len(set(ids)):raise ValueError("Duplicate "+field)
        return self

class CancelRequest(ExpectedVersion):
    reason:str=Field(min_length=1,max_length=2000)

class ScenarioCreate(Input):
    window_id:UUID
    objective_id:UUID
    name:str=Field(min_length=1,max_length=200)

class ScenarioClone(ExpectedVersion):
    name:str=Field(min_length=1,max_length=200)

class AssignmentEdit(ExpectedVersion):
    starts_at:AwareDatetime
    ends_at:AwareDatetime
    reason:str=Field(min_length=1,max_length=2000)
    team_ids:list[UUID]|None=Field(default=None,max_length=100)
    engineer_ids:list[UUID]|None=Field(default=None,max_length=200)
    asset_ids:list[UUID]|None=Field(default=None,max_length=100)
    sector_ids:list[UUID]|None=Field(default=None,min_length=1,max_length=100)
    @model_validator(mode="after")
    def valid(self):
        if self.ends_at<=self.starts_at: raise ValueError("End must follow start")
        for f in ("team_ids","engineer_ids","asset_ids","sector_ids"):
            values=getattr(self,f)
            if values is not None and len(values)!=len(set(values)): raise ValueError("Duplicate "+f)
        return self

class Preview(BaseModel):
    basic_valid:bool
    issues:list[str]
    starts_at:datetime
    ends_at:datetime
    complete_conflict_validation_performed:bool=False
    analysis_required:bool=True
    scenario_version:int

class ReadEvents(Input):
    event_ids:list[UUID]=Field(min_length=1,max_length=200)
    @model_validator(mode="after")
    def unique(self):
        if len(self.event_ids)!=len(set(self.event_ids)): raise ValueError("Duplicate event IDs")
        return self

class ReadResult(BaseModel):
    marked_read:int

class ReleaseLock(Input):
    reason:str=Field(min_length=1,max_length=2000)

class WindowOut(Named):
    starts_at:datetime
    ends_at:datetime
    timezone:str
    version:int

class ErrorBody(BaseModel):
    code:str
    message:str
    fields:list[dict[str,Any]]=Field(default_factory=list)
    correlation_id:str
    guidance:str|None=None

class ErrorResponse(BaseModel):
    error:ErrorBody

class ScenarioDetail(BaseModel):
    summary:ScenarioOut
    assignments:list[AssignmentOut]
    changes:list[dict[str,Any]]
    analysis:dict[str,Any]|None
    capabilities:Capabilities

class CommandCentre(BaseModel):
    window:WindowOut
    requests:list[RequestOut]
    timeline:list[dict[str,Any]]
    conflicts:list[dict[str,Any]]|None
    analysis:dict[str,Any]|None
    scenarios:list[ScenarioOut]
    selected_scenario_id:UUID|None
    selected_scenario_version:int|None
    capabilities:Capabilities
    truncated:bool

class Availability(BaseModel):
    resource_id:UUID
    resource_type:Literal["engineer","team","equipment"]
    availability:Literal["available","unavailable","unknown"]
    qualified:bool|None=None
    candidate_only:bool=True
    complete_allocation_validation_performed:bool=False

class Change(BaseModel):
    scenario_id:UUID
    request_id:UUID
    request_code:str
    original_start:datetime
    original_end:datetime
    starts_at:datetime
    ends_at:datetime
    reason:str
    replay_order:int

class TimelineItem(BaseModel):
    request_id:UUID
    request_code:str
    title:str
    window_id:UUID
    scenario_id:UUID|None
    starts_at:datetime
    ends_at:datetime
    original_start:datetime
    original_end:datetime
    movement_minutes:float
    moved:bool
    priority:str

class Comparison(BaseModel):
    scenarios:list[ScenarioOut]
    conflict_resolution_comparable:bool
    reason:str

class ApprovalHistory(BaseModel):
    available:bool
    reason:str
    history:Page[Entity]

class ReferenceData(BaseModel):
    priorities:list[str]
    capabilities:Capabilities
    limit_per_collection:int
    resource_lists_url:str
    collections_may_be_truncated:bool
    work_types:list[Named]
    request_statuses:list[Entity]
    equipment_types:list[Named]
    skills:list[Named]
    optimisation_objectives:list[Named]
    teams:list[Named]
    isolation_zones:list[Named]

class GeoFeature(Entity):
    type:Literal["Feature"]
    geometry:dict[str,Any]|None
    properties:dict[str,Any]
    geometry_available:bool
    geometry_source:str
    name:str

class ConflictOut(Entity):
    conflict_code:str
    analysis_run_id:UUID
    rule_id:UUID
    rule_code:str
    title:str
    explanation:str
    severity:str
    blocking:bool
    lens:str
    risk_score:float|None
    detection_method:str
    resolution_status:str
    freshness:Literal["unknown","stale","fresh"]
