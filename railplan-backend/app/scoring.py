"""Deterministic, explainable prototype scoring; never a safety clearance engine."""
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime
from hashlib import sha256
from itertools import combinations
import json
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator

ENGINE_VERSION = "railplan-scoring/1.0.0"
COMPONENTS = ("safety", "operational", "resource", "urgency", "passenger")
SEVERITIES = ("information", "low", "medium", "high", "critical")
DEFAULT_WEIGHTS = dict(zip(COMPONENTS, map(Decimal, (".35", ".25", ".20", ".10", ".10"))))

class PolicyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(default="DEMO-SEVERITY", pattern=r"^[A-Z][A-Z0-9_-]{2,63}$")
    version: int = Field(default=1, ge=1)
    weights: dict[str, Decimal] = Field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    description: str = Field(default="Synthetic prototype policy; not operationally validated", max_length=2000)

    @model_validator(mode="after")
    def validate_weights(self):
        if set(self.weights) != set(COMPONENTS):
            raise ValueError("Exactly the five named components are required")
        if any(not w.is_finite() or w < 0 or w > 1 for w in self.weights.values()):
            raise ValueError("Weights must be finite and between zero and one")
        if sum(self.weights.values()) != 1:
            raise ValueError("Weights must sum exactly to one; no renormalisation")
        if any(w.as_tuple().exponent < -6 for w in self.weights.values()):
            raise ValueError("Weights support at most six decimal places")
        return self

class ScoreCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    policy_id: UUID
    expected_conflict_version: int = Field(ge=1)
    expected_input_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    idempotency_key: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")

class Component(BaseModel):
    name: str
    score: float | None
    weight: float
    weighted_contribution: float | None
    status: Literal["complete", "partial", "unknown", "not_applicable"]
    evidence: list[str]
    missing_inputs: list[str]

class ScoreResult(BaseModel):
    engine_version: str
    rule_severity: str
    risk_score: float | None
    risk_upper_bound: float | None
    risk_band: str | None
    effective_severity: str
    blocking: bool
    score_status: Literal["complete", "partial", "unknown"]
    confidence: float
    coverage: float
    synthetic: bool
    policy_validated: bool
    eligible_for_auto_prioritisation: bool
    explanation: str
    components: list[Component]

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str, allow_nan=False)

def fingerprint(value):
    return sha256(canonical(value).encode()).hexdigest()

def rounded(value):
    return float(Decimal(value).quantize(Decimal(".01"), rounding=ROUND_HALF_UP))

def band(value):
    value = Decimal(value)
    if not value.is_finite() or not 0 <= value <= 100:
        raise ValueError("Risk must be between zero and 100")
    return SEVERITIES[min(int(value // 20), 4)]

def overlap_score(minutes):
    if minutes <= 0: return 0
    for maximum, score in ((15,20),(30,40),(60,65),(120,85)):
        if minutes <= maximum: return score
    return 100

def instant(value):
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None: raise ValueError("Timezone required")
    return parsed

def evaluate(snapshot: dict, policy: PolicyCreate) -> ScoreResult:
    """Scores known facts at fixed denominator; unknown weight defines upper bound.

    Live schema has no verified evidence/age provenance. Thus known components
    remain partial and confidence is capped; no input here can grant clearance.
    """
    rule, conflict, requests = snapshot["rule"], snapshot["conflict"], snapshot["requests"]
    severity = rule["severity"]
    minimum = max((severity, conflict["severity"]), key=SEVERITIES.index)
    synthetic = conflict["detection_method"] == "synthetic" or "synthetic" in rule["authority_reference"].lower()
    values = {name: None for name in COMPONENTS}
    evidence = {name: [] for name in COMPONENTS}
    missing = {name: ["Verified provenance and observation age"] for name in COMPONENTS}
    values["safety"] = dict(zip(SEVERITIES,(10,30,60,80,100)))[minimum]
    evidence["safety"] = [f"Rule {rule['code']} v{rule['version']}: {severity}; recorded conflict: {conflict['severity']}"]
    intervals = requests
    if snapshot.get("scenario"):
        intervals = snapshot["assignments"]
    if len(intervals) >= 2 and len(intervals) == len(requests):
        maximum = Decimal(0)
        valid = True
        for left, right in combinations(intervals, 2):
            try:
                def bounds(row):
                    start = instant(row.get("starts_at", row.get("requested_start")))
                    end = instant(row.get("ends_at", row.get("requested_end")))
                    if end <= start: raise ValueError("Reversed interval")
                    return start, end
                ls, le = bounds(left); rs, re = bounds(right)
                maximum = max(maximum, Decimal(str((min(le,re)-max(ls,rs)).total_seconds()))/60)
            except (ValueError, TypeError):
                valid = False
        if valid:
            values["operational"] = overlap_score(maximum)
            evidence["operational"] = [f"Maximum pairwise scheduled overlap: {maximum} minutes; not passenger delay"]
    if values["operational"] is None:
        missing["operational"].append("At least two complete current assignment intervals")
    # A participant link alone does not prove a capacity or compatibility violation.
    missing["resource"] += ["Verified resource collision and capacity/skill evidence"]
    evidence["resource"] = [f"Linked physical assets: {len(snapshot.get('equipment', []))}; links alone are not proof of shortage"]
    interval_by_request = {str(r.get("request_id", r.get("id"))):r for r in intervals}
    collisions = []
    for left, right in combinations(snapshot.get("allocations", []), 2):
        if (left["kind"],left["resource_id"]) != (right["kind"],right["resource_id"]) or left["request_id"] == right["request_id"]:
            continue
        a=interval_by_request.get(str(left["request_id"])); b=interval_by_request.get(str(right["request_id"]))
        if a is None or b is None: continue
        try:
            starts=[instant(r.get("starts_at",r.get("requested_start"))) for r in (a,b)]
            ends=[instant(r.get("ends_at",r.get("requested_end"))) for r in (a,b)]
            if all(end>start for start,end in zip(starts,ends)) and min(ends)>max(starts):
                collisions.append(f"{left['kind']} {left['resource_id']} assigned to overlapping requests {left['request_id']} and {right['request_id']}")
        except (ValueError,TypeError): pass
    if collisions:
        values["resource"]=80
        evidence["resource"] += sorted(set(collisions))
        missing["resource"]=["Verified provenance and observation age", "Capacity, scarcity and skill evidence; score covers observed double-booking only"]
    if requests and all(r.get("priority") in ("normal","high","urgent") for r in requests):
        values["urgency"] = max({"normal":30,"high":65,"urgent":90}[r["priority"]] for r in requests)
        evidence["urgency"] = ["Maximum participant request priority; no inferred deadline penalty"]
    else:
        missing["urgency"].append("Participant request priorities")
    missing["passenger"] += ["Verified affected passenger/service dataset"]
    subtotal = Decimal(0); coverage = Decimal(0); components = []
    for name in COMPONENTS:
        score, weight = values[name], policy.weights[name]
        contribution = None if score is None else Decimal(score) * weight
        if score is not None:
            subtotal += contribution
            coverage += weight
        components.append(Component(name=name, score=score, weight=float(weight),
            weighted_contribution=None if contribution is None else rounded(contribution),
            status="unknown" if score is None else "partial", evidence=evidence[name], missing_inputs=missing[name]))
    risk = rounded(subtotal) if coverage else None
    # Band uses the published two-decimal value to avoid display/band disagreement.
    risk_band = band(str(risk)) if risk is not None else None
    return ScoreResult(engine_version=ENGINE_VERSION, rule_severity=severity, risk_score=risk,
        risk_upper_bound=rounded(subtotal + (1-coverage)*100) if coverage else None,
        risk_band=risk_band, effective_severity=max((minimum, risk_band or minimum),key=SEVERITIES.index),
        blocking=rule["blocking"], score_status="partial" if coverage else "unknown",
        confidence=rounded(coverage * (Decimal(".25") if synthetic else Decimal(".5"))),
        coverage=float(coverage), synthetic=synthetic, policy_validated=False,
        eligible_for_auto_prioritisation=False, components=components,
        explanation="Known weighted subtotal is a lower bound, not a complete risk estimate. Unknown weights are not redistributed. Confidence reflects incomplete provenance and never scales risk. Existing rule blocking remains independent. Prototype policy is unvalidated.")
