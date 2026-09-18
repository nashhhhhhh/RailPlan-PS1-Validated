"""Versioned wire contracts. Decimal quantities are serialized as strings."""
from dataclasses import asdict, dataclass
from typing import Any, Literal, Annotated
from pydantic import BaseModel, ConfigDict, Field

VERSION = 'ps1-validator/1.1.0'
HEADERS = {
    'SCHEDULE_ACCESS.csv': 'activity_id,access_seq,week,eclo,access_night',
    'SCHEDULE_OCCUPANCY.csv': 'activity_id,week,location_id,co_share_group',
    'RESULTS.csv': 'scenario,contract_number,simulated_completion_date,overrun_days',
}
RULES = ('schema', 'unknown_reference', 'duplicate', 'workload', 'access_sequence',
         'weekly_activity_access', 'planned_start', 'dependency', 'occupancy',
         'possession_mix', 'closure', 'buffer', 'live_opposite_bound',
         'live_interchange', 'capacity', 'weekly_allocation', 'workfront',
         'eclo', 'eclo_window', 'planned_date', 'results_consistency')

@dataclass(frozen=True)
class RulePolicy:
    version: str = 'ps1-policy/4-scenario-c-line-windows'
    night_alignment: str = 'CSV-only weekly footprint overlaps are diagnostic warnings, not proof of conflict. Physical checks require complete explicit (activity_id, week) physical-night assignments; local access indices and location group labels never establish global concurrency.'
    physical_night_domain: str = 'The official inputs provide no dated engineering-night calendar. Rich optimiser validation therefore uses the optimiser-supplied explicit physical-night identity; RailPlan generation provisions a configurable uniform domain of 1 to 7 network-wide slots per calendar week.'
    eclo_line_classification: str = 'Scenario C line windows use every line present in the canonical expanded closure footprint. Non-live work affects its own line only; Live work whose interchange closure crosses H01-H02 affects both Alpha and Beta.'
    co_sharing: str = 'Pair exemption requires legal shared groups at every common occupied location. No exemption is inferred merely from a matching label at different locations.'
    separate_possessions: str = 'Distinct groups at a common occupied location are separate nights there; this does not prove separation of their buffers or mirrored closures elsewhere.'
    buffer_extent: str = 'Expand inclusive platform-ended span by two chain positions per buffer sector; clip at line ends. Mirror the full expanded Live closure.'
    interchange: str = 'Live expanded closure touching H01/H02 platforms or H01_H02 tunnel closes all three corresponding locations on both bounds of the other line; no recursive expansion.'
    completion: str = 'Completion is Sunday of the last submitted access week, provided full workload is delivered. Extra accesses remain counted.'
    dependency: str = 'Successor first week must be strictly after predecessor last access week; partial predecessors cannot release successors.'
    horizon: str = 'Access weeks must be within the supplied planning horizon.'
    priority: str = 'Sum activity overrun against its contract/type planned date times contract tier 100/10/1 and activity multiplier 1.3/1.2/1.0; contract raw overrun counted once.'
    multi_type_contract: str = 'A contract with multiple types must have consistent priority and planned completion date to derive its single RESULTS row.'
    capacity: str = 'Supply counts canonical occupied location/week groups only, not buffer or mirrored closures. Missing or conflicting group assignments use distinct synthetic slots.'
    rounding: str = 'Decimal throughout; ROUND_HALF_UP to 0.01 for score output, 0.1 for workload.'
    max_bytes: int = 4_000_000
    max_rows_per_file: int = 20_000
    max_intersecting_pairs: int = 20_000

POLICY = RulePolicy()

def snapshot():
    return asdict(POLICY)

class SubmissionInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    scenario: Literal['A', 'B', 'C']
    files: dict[str, Annotated[str, Field(max_length=4_000_000)]] = Field(max_length=3)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128, pattern=r'^\S+$')

class PreviewInput(SubmissionInput):
    instance_files: dict[str, Annotated[str, Field(max_length=4_000_000)]] = Field(min_length=8, max_length=8)

class Violation(BaseModel):
    rule_code: str
    message: str
    week: int | None = None
    activity_ids: list[str] = Field(default_factory=list)
    contract_ids: list[str] = Field(default_factory=list)
    location_ids: list[str] = Field(default_factory=list)
    possession_group: dict[str, Any] | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)

class WorkloadItem(BaseModel):
    activity_id: str
    contract_number: str
    required: str
    delivered: str
    standard_access_contribution: str
    eclo_contribution: str
    shortfall: str
    over_delivery: str
    present: bool
    complete: bool

class Completeness(BaseModel):
    activity_count: int
    activities_present: int
    activities_complete: int
    workload_gate_passed: bool
    activities: list[WorkloadItem]

class CapacityGroup(BaseModel):
    co_share_group: str
    source: str
    activity_ids: list[str]

class CapacityHotspot(BaseModel):
    location_id: str
    week: int
    supply: int
    used: int
    excess: int
    possession_groups: list[CapacityGroup]

class ActivityObjective(BaseModel):
    activity_id: str
    contract_number: str
    completion_date: str | None
    overrun_days: int | None
    weight: str
    weighted_overrun: str | None

class ContractResult(BaseModel):
    contract_number: str
    simulated_completion_date: str | None
    overrun_days: int | None

class ObjectiveComponents(BaseModel):
    overrun_days_total: int
    contracts_overrunning: int
    earliness_days_total: int
    priority_overrun: dict[str, int]
    priority_weighted_overrun: str
    excess_access_nights_total: int
    excess_penalty: str
    eclo_nights_total: int
    eclo_penalty: str
    diagnostic_objective: str
    activity_components: list[ActivityObjective]
    contract_results: list[ContractResult]
    metrics_complete: bool
    nights_scheduled: int
    formula: str

class ValidationReport(BaseModel):
    validation_context: Literal['submission', 'rich_schedule'] = 'submission'
    physical_validation_complete: bool = False
    scenario: Literal['A', 'B', 'C']
    feasible: bool
    validation_status: Literal['invalid_submission', 'infeasible', 'feasible']
    validator_version: str
    dataset_fingerprint: str
    submission_fingerprint: str
    rule_policy: dict[str, Any]
    hard_violations: list[Violation]
    warnings: list[dict[str, Any]]
    objective_components: ObjectiveComponents
    objective_score: str | None
    completeness: Completeness
    capacity_hotspots: list[CapacityHotspot]
    active_rule_assumptions: list[str]
    judge_validation: Literal['not_run'] = 'not_run'
    score_verification: Literal['internal_only'] = 'internal_only'

def violation(code, message, *, week=None, activities=(), contracts=(), locations=(), group=None, **evidence):
    assert code in RULES
    return Violation(rule_code=code, message=message, week=week,
                     activity_ids=sorted(set(activities)), contract_ids=sorted(set(contracts)),
                     location_ids=sorted(set(locations)), possession_group=group,
                     evidence=evidence).model_dump()
