"""Interfaces for future integrations. No worker is registered by this package."""
from typing import Literal,Protocol,Any
from uuid import UUID
from pydantic import BaseModel,Field

class VersionedInput(BaseModel):
    window_id:UUID
    scenario_id:UUID|None=None
    request_versions:dict[str,int]
    rule_versions:dict[str,int]
    snapshot:dict[str,Any]
    complete_solver_input:bool=False

class WorkerResult(BaseModel):
    execution_status:Literal["completed","failed","timed_out","cancelled"]
    solver_outcome:Literal["optimal","feasible","infeasible","unknown"]|None=None
    scenario_ids:list[UUID]=Field(default_factory=list)
    error_code:str|None=None
    # A timeout with solver_outcome='feasible' may contain an incumbent.
    # A domain validator must independently check it before any approval.

class AnalysisWorker(Protocol):
    def analyse(self,job_id:UUID,inputs:VersionedInput)->WorkerResult: ...

class OptimisationWorker(Protocol):
    def optimise(self,job_id:UUID,inputs:VersionedInput,objective_id:UUID)->WorkerResult: ...

class CopilotToolContext(BaseModel):
    actor_id:UUID
    operator_id:UUID
    correlation_id:UUID
    # Tool handlers must call the same authorized services as the UI.
