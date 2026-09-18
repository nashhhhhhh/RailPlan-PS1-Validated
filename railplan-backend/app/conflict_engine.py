"""Deterministic demonstration rules. Not an operational safety validator."""
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Any
import json
import logging

from fastapi import HTTPException
from sqlalchemy import text
from app import services
from app.analysis_snapshot import capture_snapshot

log = logging.getLogger(__name__)

# Stable codes are implementation identifiers, not severity or authority policy.
RULES = {
    "CE-TRACK": ("Incompatible sector occupancy", "Possession", "critical", True),
    "CE-SPATIAL": ("Workzone separation", "Possession", "critical", True),
    "CE-ISOLATION": ("Contradictory isolation states", "Isolation", "critical", True),
    "CE-ENGINEER": ("Engineer double booking", "Manpower", "high", True),
    "CE-TEAM": ("Team double booking", "Manpower", "high", True),
    "CE-ASSET": ("Equipment double booking", "Equipment", "high", True),
    "CE-AVAILABILITY": ("Resource availability", "Resources", "high", True),
    "CE-SKILL": ("Qualified headcount", "Manpower", "high", True),
    "CE-EQUIPMENT": ("Equipment quantity or capability", "Equipment", "high", True),
    "CE-WINDOW": ("Engineering window or sector availability", "Possession", "high", True),
    "CE-DEPENDENCY": ("Dependency ordering", "Dependencies", "high", True),
    "CE-TRAVEL": ("Engineer travel time", "Manpower", "high", True),
    "CE-REVIEW": ("Incomplete data requires review", "Review", "information", True),
}
SEVERITIES = ("critical", "high", "medium", "low", "information")
PARTICIPANTS = {
    "request_ids": ("conflict_requests", "request_id"),
    "team_ids": ("conflict_teams", "team_id"),
    "engineer_ids": ("conflict_engineers", "engineer_id"),
    "equipment_ids": ("conflict_equipment", "asset_id"),
    "sector_ids": ("conflict_sectors", "sector_id"),
    "isolation_zone_ids": ("conflict_isolations", "isolation_zone_id"),
}


@dataclass(frozen=True)
class ConflictFinding:
    rule_code: str
    title: str
    explanation: str
    request_ids: tuple[str, ...]
    team_ids: tuple[str, ...] = ()
    engineer_ids: tuple[str, ...] = ()
    equipment_ids: tuple[str, ...] = ()
    sector_ids: tuple[str, ...] = ()
    isolation_zone_ids: tuple[str, ...] = ()
    evidence: dict[str, Any] = field(default_factory=dict)


class ConfigurationError(ValueError):
    pass


def instant(value):
    return value if isinstance(value, datetime) else datetime.fromisoformat(value)


def interval(row):
    return instant(row["starts_at"]), instant(row["ends_at"])


def overlaps(a, b):
    return a[0] < b[1] and b[0] < a[1]


def covers(periods, target):
    """Union coverage: contiguous rows cover, a gap of any size does not."""
    cursor = target[0]
    for start, end in sorted(periods):
        if start > cursor:
            break
        cursor = max(cursor, end)
        if cursor >= target[1]:
            return True
    return False


def available(rows, target):
    return covers([interval(r) for r in rows if r["available"]], target) and not any(
        overlaps(interval(r), target) for r in rows if not r["available"]
    )


def merge_intervals(periods):
    """Union overlapping/adjacent deployment intervals without filling gaps."""
    merged = []
    for start, end in sorted(set(periods)):
        if start >= end:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def grouped(rows, key):
    result = defaultdict(list)
    for row in rows:
        result[row[key]].append(row)
    return result


def resolve_rules(rows):
    latest = {}
    for row in rows:
        if row["code"] not in latest or row["version"] > latest[row["code"]]["version"]:
            latest[row["code"]] = row
    missing = [code for code in RULES if code not in latest or not latest[code]["enabled"]]
    if missing:
        raise ConfigurationError("Missing or disabled required rule definitions: " + ", ".join(sorted(missing)))
    return {code: latest[code] for code in sorted(RULES)}


class Evaluator:
    def __init__(self, snapshot):
        self.data = snapshot
        self.jobs = {r["id"]: r for r in snapshot["jobs"]}
        self.relations = {k: grouped(snapshot.get(k, []), "request_id") for k in (
            "sectors", "teams", "engineers", "assets", "isolations", "zones",
            "required_skills", "required_equipment", "required_capabilities")}
        self.calendars = {
            kind: grouped(snapshot.get(table, []), key) for kind, table, key in (
                ("engineer", "engineer_availability", "engineer_id"),
                ("team", "team_availability", "team_id"),
                ("asset", "equipment_availability", "asset_id"),
                ("sector", "sector_availability", "sector_id"))}
        self.records = {
            kind: {r["id"]: r for r in snapshot.get(table, [])}
            for kind, table in (("engineer", "engineer_records"), ("asset", "asset_records"), ("team", "team_records"))}
        self.findings = []
        self.skills = grouped(snapshot.get("skills", []), "engineer_id")
        self.capabilities = grouped(snapshot.get("asset_capabilities", []), "asset_id")
        self.memberships = grouped(snapshot.get("memberships", []), "team_id")
        self.isolation_records = {r["id"]: r for r in snapshot.get("isolation_records", [])}

    def ids(self, relation, rid, key):
        return {r[key] for r in self.relations[relation][rid]}

    def emit(self, code, requests, reason, evidence=None, **participants):
        ids = tuple(sorted(set(requests)))
        labels = ", ".join(self.jobs.get(r, {}).get("request_code", r) for r in ids)
        self.findings.append(ConflictFinding(
            code, RULES[code][0], f"{labels}: {reason}", ids,
            **{key: tuple(sorted(set(value))) for key, value in participants.items()},
            evidence=evidence or {}))

    def resource_ok(self, kind, resource, target):
        record = self.records[kind].get(resource)
        return bool(record and record.get("active", True) and available(self.calendars[kind][resource], target))

    def single_jobs(self):
        window = interval(self.data["window"])
        for rid, job in sorted(self.jobs.items()):
            target = interval(job)
            time_label = f"[{target[0].isoformat()}, {target[1].isoformat()})"
            if target[0] < window[0] or target[1] > window[1]:
                self.emit("CE-WINDOW", [rid], f"work {time_label} lies outside engineering window {window}.")
            if job.get("assignment_version", job.get("version")) != job.get("version"):
                self.emit("CE-REVIEW", [rid], "scenario assignment references a stale request version.")
            sectors = self.ids("sectors", rid, "sector_id")
            if not sectors:
                self.emit("CE-REVIEW", [rid], "no assigned sector; location cannot be validated.")
            for sector in sorted(sectors):
                if not available(self.calendars["sector"][sector], target):
                    self.emit("CE-WINDOW", [rid], f"sector {sector} lacks complete permitted coverage or has an unavailable interval for {time_label}.", sector_ids=[sector])
            for kind, relation, key, participant in (
                ("engineer", "engineers", "engineer_id", "engineer_ids"),
                ("team", "teams", "team_id", "team_ids"),
                ("asset", "assets", "asset_id", "equipment_ids")):
                for resource in sorted(self.ids(relation, rid, key)):
                    periods = merge_intervals([interval(r) for r in self.relations[relation][rid]
                        if r[key] == resource]) if kind == "engineer" else [target]
                    missing = [p for p in periods if not self.resource_ok(kind, resource, p)]
                    if missing:
                        label = "; ".join(f"[{a.isoformat()}, {b.isoformat()})" for a, b in missing)
                        self.emit("CE-AVAILABILITY", [rid], f"{kind} {resource} is inactive, explicitly unavailable, or lacks full availability coverage for assigned interval(s) {label}.", **{participant: [resource]})
            # A team is not assumed to be an unlimited anonymous pool.
            for team in self.ids("teams", rid, "team_id"):
                if not covers([interval(m) for m in self.memberships[team]], target):
                    self.emit("CE-REVIEW", [rid], f"team {team} lacks effective member coverage throughout this work interval.", team_ids=[team])
            assigned = grouped(self.relations["engineers"][rid], "engineer_id")
            for requirement in self.relations["required_skills"][rid]:
                skill = requirement["skill_id"]
                qualified = {eid for eid, slots in assigned.items()
                    if covers([interval(r) for r in slots], target)
                    and self.resource_ok("engineer", eid, target)
                    and covers([interval(r) for r in self.skills[eid] if r["skill_id"] == skill], target)}
                if len(qualified) < requirement["required_count"]:
                    self.emit("CE-SKILL", [rid], f"skill {skill} requires {requirement['required_count']} engineers; {len(qualified)} distinct assigned engineers have valid full-interval qualifications and availability.",
                              {"skill_id": skill, "required": requirement["required_count"], "qualified": len(qualified)}, engineer_ids=assigned)
            assets = self.ids("assets", rid, "asset_id")
            valid = {a for a in assets if self.resource_ok("asset", a, target)}
            for requirement in self.relations["required_equipment"][rid]:
                matching = {a for a in valid if self.records["asset"][a]["type_id"] == requirement["type_id"]}
                if len(matching) < requirement["quantity"]:
                    self.emit("CE-EQUIPMENT", [rid], f"equipment type {requirement['type_id']} requires quantity {requirement['quantity']}; valid assigned quantity is {len(matching)}.",
                              {"type_id": requirement["type_id"], "required": requirement["quantity"], "assigned": len(matching)}, equipment_ids=assets)
            provided = {c["capability_id"] for a in valid for c in self.capabilities[a]}
            missing = self.ids("required_capabilities", rid, "capability_id") - provided
            if missing:
                self.emit("CE-EQUIPMENT", [rid], f"available assigned assets lack required capabilities: {', '.join(sorted(missing))}.", {"missing_capabilities": sorted(missing)}, equipment_ids=assets)
        for job in self.data.get("unassigned", []):
            self.emit("CE-REVIEW", [job["id"]], f"{job['request_code']} has no assignment in this scenario; it was not evaluated.")

    def pairs(self):
        compatibility = {}
        for c in self.data.get("compatibility", []):
            key = tuple(sorted((c["first_work_type_id"], c["second_work_type_id"])))
            if key not in compatibility or c["version"] > compatibility[key]["version"]:
                compatibility[key] = c
        spatial = defaultdict(list)
        for s in self.data.get("spatial", []):
            spatial[tuple(sorted((s["first_id"], s["second_id"])))].append(s)
        for p in self.data.get("pairs", []):
            a, b = sorted((p["first_id"], p["second_id"]))
            ja, jb = self.jobs[a], self.jobs[b]
            overlap = (max(interval(ja)[0], interval(jb)[0]), min(interval(ja)[1], interval(jb)[1]))
            if overlap[0] >= overlap[1]:
                continue
            timing = f"during [{overlap[0].isoformat()}, {overlap[1].isoformat()})"
            shared = self.ids("sectors", a, "sector_id") & self.ids("sectors", b, "sector_id")
            c = compatibility.get(tuple(sorted((ja["work_type_id"], jb["work_type_id"]))))
            za, zb = self.relations["zones"][a], self.relations["zones"][b]
            if c is None and (shared or (za and zb)):
                self.emit("CE-REVIEW", [a, b], f"no compatibility decision for work types {ja['work_type_id']} and {jb['work_type_id']} {timing}.", sector_ids=shared)
            if c and shared and not c["compatible"]:
                self.emit("CE-TRACK", [a, b], f"incompatible work shares sectors {', '.join(sorted(shared))} {timing}; compatibility version {c['version']}.", {"compatibility_id": c["id"]}, sector_ids=shared)
            if shared or za or zb or (c and float(c["minimum_separation_metres"]) > 0):
                if not za or not zb or not all(z["usable"] for z in za + zb):
                    self.emit("CE-REVIEW", [a, b], f"missing, empty, invalid or unverified workzone geometry; spatial safety cannot be evaluated {timing}.", sector_ids=shared)
                elif c:
                    limit = float(c["minimum_separation_metres"])
                    hits = [s for s in spatial[(a, b)] if s["intersects"] or
                            (s["within_limit"] and s["distance_metres"] is not None and float(s["distance_metres"]) < limit)]
                    if hits:
                        distance = min(float(s["distance_metres"]) for s in hits)
                        self.emit("CE-SPATIAL", [a, b], f"workzones intersect/touch or have distance {distance:.3f} m below required {limit:g} m {timing}.",
                                  {"distance_metres": distance, "minimum_separation_metres": limit, "zone_pairs": hits}, sector_ids=self.ids("sectors", a, "sector_id") | self.ids("sectors", b, "sector_id"))
            ia = {r["isolation_zone_id"]: r["required_state"] for r in self.relations["isolations"][a]}
            ib = {r["isolation_zone_id"]: r["required_state"] for r in self.relations["isolations"][b]}
            for zone in sorted(ia.keys() & ib.keys()):
                if ia[zone] != ib[zone]:
                    record = self.isolation_records.get(zone, {})
                    label = record.get("name", zone)
                    self.emit("CE-ISOLATION", [a, b], f"zone {label} ({zone}) requires {ia[zone]} for {ja['request_code']} and {ib[zone]} for {jb['request_code']} {timing}.", isolation_zone_ids=[zone])
            for relation, key, code, participant in (
                ("teams", "team_id", "CE-TEAM", "team_ids"),
                ("assets", "asset_id", "CE-ASSET", "equipment_ids"),
                ("engineers", "engineer_id", "CE-ENGINEER", "engineer_ids")):
                for resource in sorted(self.ids(relation, a, key) & self.ids(relation, b, key)):
                    if relation == "engineers" and not any(overlaps(interval(x), interval(y))
                        for x in self.relations[relation][a] for y in self.relations[relation][b]
                        if x[key] == resource and y[key] == resource):
                        continue
                    self.emit(code, [a, b], f"shared {key} {resource} is double booked {timing}.", **{participant: [resource]})

    def dependencies(self):
        for d in self.data.get("dependencies", []):
            a, b = d["predecessor_id"], d["successor_id"]
            participants = [r for r in (a, b) if r in self.jobs]
            if not participants:
                continue
            if a not in self.jobs or b not in self.jobs:
                self.emit("CE-REVIEW", participants, f"dependency {d['id']} has an endpoint outside the evaluated schedule; ordering is unknown.")
                continue
            code = d["code"]
            if code not in ("finish_to_start", "start_to_start", "finish_to_finish"):
                self.emit("CE-REVIEW", participants, f"dependency {d['id']} type {code} has no configured state-transition semantics.")
                continue
            before = interval(self.jobs[a])[0 if code == "start_to_start" else 1]
            after = interval(self.jobs[b])[1 if code == "finish_to_finish" else 0]
            required = before + timedelta(minutes=d["lag_minutes"])
            if after < required:
                self.emit("CE-DEPENDENCY", participants, f"{code} dependency {d['id']} from {a} to {b} requires successor boundary >= {required.isoformat()} including {d['lag_minutes']} min lag; actual {after.isoformat()}.", {"dependency_id": d["id"]})

    def travel(self):
        if not self.data.get("scenario"):
            return
        routes = {(r["from_sector_id"], r["to_sector_id"]): r["minutes"] for r in self.data.get("travel", [])}
        deployments = defaultdict(list)
        for row in self.data.get("engineers", []):
            deployments[(row["engineer_id"], row["request_id"])].append(interval(row))
        bookings = defaultdict(list)
        for (eid, rid), periods in deployments.items():
            for start, end in merge_intervals(periods):
                bookings[eid].append((start, end, rid))
        for eid, slots in sorted(bookings.items()):
            # Merge overlapping work into groups; compare every boundary pair of
            # neighbouring groups so a long overlapping job cannot hide a violation.
            groups = []
            for start, end, rid in sorted(slots):
                slot = (start, end, rid)
                if groups and start < groups[-1][1]:
                    groups[-1][0].append(slot)
                    groups[-1][1] = max(groups[-1][1], end)
                else:
                    groups.append([[slot], end])
            for left, right in zip(groups, groups[1:]):
                for a_start, a_end, a in left[0]:
                    for b_start, b_end, b in right[0]:
                        if a == b:
                            continue  # Same job resumed; there is no location transfer.
                        sa, sb = self.ids("sectors", a, "sector_id"), self.ids("sectors", b, "sector_id")
                        if len(sa) != 1 or len(sb) != 1:
                            self.emit("CE-REVIEW", [a, b], f"engineer {eid}: multi-sector or missing location has no travel endpoint policy.", engineer_ids=[eid])
                            continue
                        route = (next(iter(sa)), next(iter(sb)))
                        if route not in routes:
                            self.emit("CE-REVIEW", [a, b], f"engineer {eid}: no configured directed travel time from {route[0]} to {route[1]}; zero is not assumed.", engineer_ids=[eid], sector_ids=route)
                            continue
                        gap = (b_start - a_end).total_seconds() / 60
                        if gap < routes[route]:
                            self.emit("CE-TRAVEL", [a, b], f"engineer {eid} has {gap:g} min between assignment end {a_end.isoformat()} on {a} and assignment start {b_start.isoformat()} on {b}; route requires {routes[route]} min.", {"gap_minutes": gap, "required_minutes": routes[route], "assignment_end": a_end.isoformat(), "next_assignment_start": b_start.isoformat()}, engineer_ids=[eid], sector_ids=route)

    def run(self):
        self.single_jobs()
        self.pairs()
        self.dependencies()
        self.travel()
        # Evidence distinguishes e.g. two missing skill requirements on one job.
        unique = {json.dumps(asdict(f), sort_keys=True, default=str): f for f in self.findings}
        return [unique[k] for k in sorted(unique)]


def evaluate(snapshot):
    resolve_rules(snapshot["rules"])
    return Evaluator(snapshot).run()


def run_conflict_analysis(db, analysis_run_id):
    run = services.one(db, "SELECT * FROM railplan.analysis_runs WHERE id=:id FOR UPDATE", id=analysis_run_id)
    if run is None:
        raise HTTPException(404, "Analysis not found")
    if run["status"] != "queued":
        raise HTTPException(409, "Analysis has already started; create a new run")
    db.execute(text("UPDATE railplan.analysis_runs SET status='running' WHERE id=:id"), {"id": analysis_run_id})
    snapshot = None
    try:
        with db.begin_nested():
            snapshot = capture_snapshot(db, run["window_id"], run["scenario_id"])
            rules = resolve_rules(snapshot["rules"])
            findings = evaluate(snapshot)
            evidence = []
            for finding in findings:
                rule = rules[finding.rule_code]
                cid = services.put(db, "conflicts", analysis_run_id=analysis_run_id, rule_id=rule["id"],
                    title=rule["name"], explanation=finding.explanation, severity=rule["severity"],
                    risk_score=None, detection_method="automatic", resolution_status="open")
                for field_name, (table, column) in PARTICIPANTS.items():
                    for participant in getattr(finding, field_name):
                        services.put(db, table, conflict_id=cid, **{column: participant})
                evidence.append({"conflict_id": str(cid), **asdict(finding)})
            snapshot["finding_evidence"] = evidence
            # Persist exact policy + input used. Read endpoints never derive old
            # severity/blocking decisions from mutable current rule definitions.
            db.execute(text("""UPDATE railplan.analysis_runs SET input_snapshot=CAST(:snapshot AS jsonb),
                rule_snapshot=CAST(:rules AS jsonb),status='completed',completed_at=clock_timestamp()
                WHERE id=:id"""), {"id": analysis_run_id, "snapshot": json.dumps(snapshot, default=str),
                                    "rules": json.dumps(list(rules.values()), default=str)})
    except Exception as exc:
        # Savepoint removed every partial finding. The endpoint returns a response
        # rather than raising, allowing the outer request transaction to commit failure.
        message = str(exc) if isinstance(exc, ConfigurationError) else "Analysis failed; no partial results were saved."
        failed_snapshot = snapshot if snapshot is not None else dict(run["input_snapshot"])
        failed_snapshot["error"] = message
        # Do not retain IDs of rolled-back partial findings in a failed snapshot.
        failed_snapshot.pop("finding_evidence", None)
        db.execute(text("""UPDATE railplan.analysis_runs SET status='failed',completed_at=clock_timestamp(),
          input_snapshot=CAST(:snapshot AS jsonb),rule_snapshot=CAST(:rules AS jsonb) WHERE id=:id"""),
          {"id": analysis_run_id, "snapshot": json.dumps(failed_snapshot, default=str),
           "rules": json.dumps(failed_snapshot.get("rules", []), default=str)})
        log.warning("Conflict analysis %s failed (%s)", analysis_run_id, type(exc).__name__)
        return analysis_summary(db, analysis_run_id)
    return analysis_summary(db, analysis_run_id)


def analysis_summary(db, analysis_run_id):
    run = services.one(db, "SELECT * FROM railplan.analysis_runs WHERE id=:id", id=analysis_run_id)
    if run is None:
        raise HTTPException(404, "Analysis not found")
    rows = db.execute(text("SELECT rule_id,severity FROM railplan.conflicts WHERE analysis_run_id=:id"), {"id": analysis_run_id}).mappings().all()
    rules = {r["id"]: r for r in run["rule_snapshot"]} if isinstance(run["rule_snapshot"], list) else {}
    severity = Counter(r["severity"] for r in rows)
    categories = Counter(rules.get(str(r["rule_id"]), {}).get("category", "Synthetic") for r in rows)
    return {"id": str(run["id"]), "status": run["status"], "window_id": str(run["window_id"]),
        "scenario_id": str(run["scenario_id"]) if run["scenario_id"] else None,
        "completed_at": run["completed_at"], "conflict_count": len(rows),
        "blocking_conflict_count": sum(bool(rules.get(str(r["rule_id"]), {}).get("blocking", True)) for r in rows),
        "counts_by_severity": {s: severity[s] for s in SEVERITIES},
        "counts_by_category": dict(sorted(categories.items())),
        "scope": "single_window", "operationally_validated": False,
        "freshness": "unknown", "can_certify_current_schedule": False,
        "detail": run["input_snapshot"].get("error")}


def require_analysis(db, analysis_run_id, actor):
    run = services.one(db, "SELECT * FROM railplan.analysis_runs WHERE id=:id", id=analysis_run_id)
    if run is None:
        raise HTTPException(404, "Analysis not found")
    services.require_window(db, run["window_id"], actor)
    return run


def conflict_details(db, analysis_run_id):
    # Fixed six joins through separate aggregates avoid Cartesian multiplication.
    expressions = []
    for field_name, (table, column) in PARTICIPANTS.items():
        expressions.append(f"'{field_name}',(SELECT coalesce(jsonb_agg(p.{column} ORDER BY p.{column}),'[]'::jsonb) FROM railplan.{table} p WHERE p.conflict_id=c.id)")
    sql = """SELECT to_jsonb(c) || jsonb_build_object(""" + ",".join(expressions) + """,
      'rule_code',coalesce(s.rule->>'code',r.code),
      'rule_version',coalesce((s.rule->>'version')::integer,r.version),
      'category',coalesce(s.rule->>'category',r.category),
      'blocking',coalesce((s.rule->>'blocking')::boolean,r.blocking)) AS doc
      FROM railplan.conflicts c JOIN railplan.analysis_runs a ON a.id=c.analysis_run_id
      JOIN railplan.rule_definitions r ON r.id=c.rule_id
      LEFT JOIN LATERAL (SELECT value AS rule FROM jsonb_array_elements(
        CASE WHEN jsonb_typeof(a.rule_snapshot)='array' THEN a.rule_snapshot ELSE '[]'::jsonb END)
        WHERE value->>'id'=c.rule_id::text LIMIT 1) s ON true
      WHERE c.analysis_run_id=:id ORDER BY c.conflict_code"""
    return db.execute(text(sql), {"id": analysis_run_id}).scalars().all()
