from copy import deepcopy
from datetime import datetime, timedelta, timezone
import re

import pytest
from pglast import parse_sql
from fastapi.testclient import TestClient
from app.analysis_snapshot import SNAPSHOT_SQL
from app.conflict_engine import RULES, ConfigurationError, evaluate, overlaps, covers, resolve_rules
from app.main import app


def at(minutes):
    return (datetime(2026, 9, 14, tzinfo=timezone.utc) + timedelta(minutes=minutes)).isoformat()


def rule_rows():
    return [dict(id=code, code=code, name=name, category=category, severity=severity,
                 blocking=blocking, enabled=True, version=1, parameters={})
            for code, (name, category, severity, blocking) in RULES.items()]


def schedule():
    jobs = [dict(id=rid, request_code=rid, work_type_id=typ, version=1, assignment_version=1,
                 starts_at=at(start), ends_at=at(end))
            for rid, typ, start, end in (("A", "type-A", 10, 40), ("B", "type-B", 30, 60))]
    return dict(jobs=jobs, rules=rule_rows(), window=dict(starts_at=at(0), ends_at=at(120)),
        scenario=None, sectors=[dict(request_id=r, sector_id="sector") for r in ("A", "B")],
        sector_availability=[dict(sector_id="sector", starts_at=at(0), ends_at=at(120), available=True)],
        pairs=[dict(first_id="A", second_id="B")],
        compatibility=[dict(id="compat", first_work_type_id="type-A", second_work_type_id="type-B",
                            compatible=False, version=1, minimum_separation_metres=10)],
        zones=[dict(request_id=r, id="zone-"+r, usable=True) for r in ("A", "B")],
        spatial=[dict(first_id="A", second_id="B", first_zone_id="zone-A", second_zone_id="zone-B",
                      intersects=False, distance_metres=50, within_limit=False)])


def findings(data, code):
    return [f for f in evaluate(data) if f.rule_code == code]


def assign(data, kind, resource="shared", requests=("A", "B")):
    relation, key, records, calendar = {
        "engineer": ("engineers", "engineer_id", "engineer_records", "engineer_availability"),
        "team": ("teams", "team_id", "team_records", "team_availability"),
        "asset": ("assets", "asset_id", "asset_records", "equipment_availability"),
    }[kind]
    for rid in requests:
        job = next(j for j in data["jobs"] if j["id"] == rid)
        data.setdefault(relation, []).append(dict(request_id=rid, **{key: resource},
            starts_at=job["starts_at"], ends_at=job["ends_at"]))
    data.setdefault(records, []).append(dict(id=resource, active=True, type_id="tool"))
    data.setdefault(calendar, []).append(dict(**{key: resource}, starts_at=at(0), ends_at=at(120), available=True))


def test_half_open_and_union_coverage():
    t = lambda a, b: (datetime.fromisoformat(at(a)), datetime.fromisoformat(at(b)))
    assert not overlaps(t(0, 10), t(10, 20))
    assert covers([t(0, 10), t(10, 20)], t(0, 20))
    assert not covers([t(0, 9), t(10, 20)], t(0, 20))
    data = schedule()
    data["jobs"][1]["starts_at"] = at(40)
    assert not findings(data, "CE-TRACK")


def test_track_and_multisector_deduplication():
    data = schedule()
    data["sectors"] += [dict(request_id=r, sector_id="second") for r in ("A", "B")]
    result = findings(data, "CE-TRACK")
    assert len(result) == 1
    assert result[0].sector_ids == ("second", "sector")


def test_compatible_latest_version_and_missing_policy():
    data = schedule()
    data["compatibility"].append({**data["compatibility"][0], "version": 2, "compatible": True})
    assert not findings(data, "CE-TRACK")
    data["compatibility"] = []
    assert any("no compatibility" in f.explanation for f in findings(data, "CE-REVIEW"))


@pytest.mark.parametrize("intersects,distance,within,expected", [(True, 0, True, True),
    (False, 9, True, True), (False, 10, True, False), (False, 11, False, False)])
def test_spatial_boundaries(intersects, distance, within, expected):
    data = schedule()
    data["spatial"][0].update(intersects=intersects, distance_metres=distance, within_limit=within)
    assert bool(findings(data, "CE-SPATIAL")) is expected


@pytest.mark.parametrize("zones", [[], [dict(request_id="A", id="z", usable=False)]])
def test_missing_geometry_not_safe(zones):
    data = schedule()
    data["zones"] = zones
    assert any("geometry" in f.explanation for f in findings(data, "CE-REVIEW"))


def test_isolation_states():
    data = schedule()
    data["isolations"] = [dict(request_id=r, isolation_zone_id="P4", required_state=s)
                          for r, s in (("A", "isolated"), ("B", "restored"))]
    assert findings(data, "CE-ISOLATION")[0].isolation_zone_ids == ("P4",)
    data["isolations"][1]["required_state"] = "isolated"
    assert not findings(data, "CE-ISOLATION")


@pytest.mark.parametrize("kind,code", [("engineer", "CE-ENGINEER"), ("team", "CE-TEAM"), ("asset", "CE-ASSET")])
def test_double_booking(kind, code):
    data = schedule()
    assign(data, kind)
    assert len(findings(data, code)) == 1


def test_different_assets_of_same_type():
    data = schedule()
    assign(data, "asset", "asset-A", ("A",))
    assign(data, "asset", "asset-B", ("B",))
    assert not findings(data, "CE-ASSET")


def test_deduplicate_direct_and_team_engineer_and_partial_membership():
    data = schedule()
    assign(data, "engineer")
    data["engineers"] *= 2
    assert len(findings(data, "CE-ENGINEER")) == 1
    for r in data["engineers"]:
        if r["request_id"] == "A":
            r["ends_at"] = at(20)
    assert not findings(data, "CE-ENGINEER")


@pytest.mark.parametrize("kind,calendar", [("engineer", "engineer_availability"),
    ("team", "team_availability"), ("asset", "equipment_availability")])
@pytest.mark.parametrize("mode", ["missing", "unavailable", "gap"])
def test_resource_unavailability(kind, calendar, mode):
    data = schedule()
    assign(data, kind, requests=("A",))
    if mode == "missing":
        data[calendar] = []
    elif mode == "unavailable":
        data[calendar].append({**data[calendar][0], "available": False, "starts_at": at(20), "ends_at": at(21)})
    else:
        data[calendar][0]["ends_at"] = at(39)
    assert len(findings(data, "CE-AVAILABILITY")) == 1


@pytest.mark.parametrize("kind,record", [("engineer", "engineer_records"), ("asset", "asset_records")])
def test_inactive_resource(kind, record):
    data = schedule()
    assign(data, kind, requests=("A",))
    data[record][0]["active"] = False
    assert findings(data, "CE-AVAILABILITY")


def test_skill_expiry_headcount_and_dedup():
    data = schedule()
    assign(data, "engineer", requests=("A",))
    data["required_skills"] = [dict(request_id="A", skill_id="skill", required_count=1)]
    data["skills"] = [dict(engineer_id="shared", skill_id="skill", starts_at=at(0), ends_at=at(120))]
    assert not findings(data, "CE-SKILL")
    data["skills"][0]["ends_at"] = at(39)
    assert findings(data, "CE-SKILL")[0].evidence["qualified"] == 0
    data["skills"][0]["ends_at"] = at(120)
    data["engineers"] *= 2
    data["required_skills"][0]["required_count"] = 2
    assert findings(data, "CE-SKILL")[0].evidence["qualified"] == 1
    data["required_skills"][0]["required_count"] = 1
    for r in data["engineers"]:
        r["ends_at"] = at(30)
    assert findings(data, "CE-SKILL")


def test_equipment_quantity_capability_and_dedup():
    data = schedule()
    assign(data, "asset", requests=("A",))
    data["assets"] *= 2
    data["required_equipment"] = [dict(request_id="A", type_id="tool", quantity=2)]
    assert findings(data, "CE-EQUIPMENT")[0].evidence["assigned"] == 1
    data["required_equipment"][0]["quantity"] = 1
    data["required_capabilities"] = [dict(request_id="A", capability_id="cap")]
    assert findings(data, "CE-EQUIPMENT")[0].evidence["missing_capabilities"] == ["cap"]
    data["asset_capabilities"] = [dict(asset_id="shared", capability_id="cap")]
    assert not findings(data, "CE-EQUIPMENT")


def test_window_and_sector_availability():
    data = schedule()
    data["window"]["ends_at"] = at(50)
    assert len(findings(data, "CE-WINDOW")) == 1
    data["sector_availability"] = []
    assert len(findings(data, "CE-WINDOW")) == 3


@pytest.mark.parametrize("code,lag,expected", [("finish_to_start", 0, True),
    ("start_to_start", 20, False), ("start_to_start", 21, True),
    ("finish_to_finish", 20, False), ("finish_to_finish", 21, True)])
def test_dependencies(code, lag, expected):
    data = schedule()
    data["dependencies"] = [dict(id="dependency", predecessor_id="A", successor_id="B", code=code, lag_minutes=lag)]
    assert bool(findings(data, "CE-DEPENDENCY")) is expected


def test_unsupported_and_out_of_scope_dependency():
    data = schedule()
    data["dependencies"] = [dict(id="d", predecessor_id="A", successor_id="B", code="requires_handback", lag_minutes=0)]
    assert findings(data, "CE-REVIEW")
    data["dependencies"][0]["successor_id"] = "outside"
    assert "outside" in findings(data, "CE-REVIEW")[0].explanation


def test_travel_and_missing_route():
    data = schedule()
    data["scenario"] = dict(id="scenario")
    data["jobs"][1]["starts_at"] = at(45)
    assign(data, "engineer")
    assert any("travel time" in f.explanation for f in findings(data, "CE-REVIEW"))
    data["travel"] = [dict(from_sector_id="sector", to_sector_id="sector", minutes=6)]
    assert len(findings(data, "CE-TRAVEL")) == 1
    data["travel"][0]["minutes"] = 5
    assert not findings(data, "CE-TRAVEL")
    data["scenario"] = None
    data["travel"][0]["minutes"] = 100
    assert not findings(data, "CE-TRAVEL")


def test_missing_and_disabled_rule_fails_closed():
    data = schedule()
    data["rules"][0]["enabled"] = False
    with pytest.raises(ConfigurationError, match="disabled"):
        evaluate(data)
    data["rules"] = []
    with pytest.raises(ConfigurationError, match="Missing"):
        evaluate(data)


def test_latest_disabled_does_not_fall_back_to_old_version():
    data = schedule()
    data["rules"].append({**data["rules"][0], "version": 2, "enabled": False})
    with pytest.raises(ConfigurationError):
        resolve_rules(data["rules"])


def test_deterministic_results_and_no_input_mutation():
    data = schedule()
    copy = deepcopy(data)
    first = evaluate(data)
    data["jobs"].reverse()
    data["pairs"] *= 2
    assert evaluate(data) == first
    assert evaluate(copy) == first


def test_snapshot_sql_parses():
    names = {}
    def replace(match):
        names.setdefault(match[1], len(names) + 1)
        return "$" + str(names[match[1]])
    assert parse_sql(re.sub(r"(?<!:):([a-zA-Z_]\w*)", replace, SNAPSHOT_SQL))


def test_openapi_new_routes_and_health():
    with TestClient(app) as client:
        paths = client.get("/openapi.json").json()["paths"]
        for path in ("/api/analyses/{analysis_id}", "/api/analyses/{analysis_id}/conflicts", "/api/conflicts/{conflict_id}"):
            assert path in paths
        health = client.get("/health").json()
        assert health["conflict_engine_available"]
        assert health["solver_available"] and health["stateless_scenario_a_preview"]
        assert not health["operational_approval_available"]


def test_new_migration_preserves_initial_assets(monkeypatch):
    import importlib
    revision = importlib.import_module("migrations.versions.0004_analysis_history")
    calls = []
    class Connection:
        def exec_driver_sql(self, sql, **options):
            assert options["execution_options"]["no_parameters"] is True
            assert parse_sql(sql)
            calls.append(sql)
    monkeypatch.setattr(revision.op, "get_bind", lambda: Connection())
    revision.upgrade()
    assert len(calls) == 1
    assert "CREATE OR REPLACE VIEW coordination_queue" in calls[0]
    assert revision.down_revision == "0003"
    with pytest.raises(RuntimeError):
        revision.downgrade()


def test_missing_scenario_assignment_and_stale_version_are_review_findings():
    data = schedule()
    data["unassigned"] = [dict(id="C", request_code="MR-C")]
    data["jobs"][0]["assignment_version"] = 0
    result = findings(data, "CE-REVIEW")
    assert len(result) == 2
    assert any("stale" in r.explanation for r in result)
    assert any("no assignment" in r.explanation for r in result)


def test_team_membership_gaps_require_review():
    data = schedule()
    assign(data, "team", requests=("A",))
    data["memberships"] = [dict(team_id="shared", engineer_id="e", starts_at=at(10), ends_at=at(40))]
    assert not findings(data, "CE-REVIEW")
    data["memberships"][0]["ends_at"] = at(39)
    assert findings(data, "CE-REVIEW")


def test_travel_uses_partial_engineer_intervals_not_whole_jobs():
    data = schedule()
    data["scenario"] = {"id": "scenario"}
    assign(data, "engineer")
    data["engineers"][0]["ends_at"] = at(20)
    data["travel"] = [dict(from_sector_id="sector", to_sector_id="sector", minutes=20)]
    assert not findings(data, "CE-ENGINEER")
    result = findings(data, "CE-TRAVEL")
    assert len(result) == 1
    assert result[0].evidence["gap_minutes"] == 10
    data["engineers"] *= 2  # Direct/team duplicates cannot double-count travel.
    assert findings(data, "CE-TRAVEL") == result
    data["travel"][0]["minutes"] = 10
    assert not findings(data, "CE-TRAVEL")


def test_partial_assignment_availability_only_checks_deployment():
    data = schedule()
    assign(data, "engineer", requests=("A",))
    data["engineers"][0]["ends_at"] = at(20)
    data["engineer_availability"][0].update(starts_at=at(10), ends_at=at(20))
    assert not findings(data, "CE-AVAILABILITY")
    data["engineer_availability"][0]["ends_at"] = at(19)
    assert findings(data, "CE-AVAILABILITY")


def test_split_deployment_preserves_gap_and_return_travel():
    data = schedule()
    data["scenario"] = {"id": "scenario"}
    data["jobs"][0]["ends_at"] = at(100)
    assign(data, "engineer")
    first = data["engineers"][0]
    first["ends_at"] = at(20)
    data["engineers"].append({**first, "starts_at": at(65), "ends_at": at(100)})
    data["travel"] = [dict(from_sector_id="sector", to_sector_id="sector", minutes=20)]
    result = findings(data, "CE-TRAVEL")
    assert len(result) == 2
    assert {r.evidence["gap_minutes"] for r in result} == {5, 10}


def test_cors_allows_local_analysis_headers_but_not_unlisted_origin():
    with TestClient(app) as client:
        headers = {"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST",
                   "Access-Control-Request-Headers": "content-type,x-demo-user-id"}
        response = client.options("/api/analyses", headers=headers)
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == headers["Origin"]
        response = client.options("/api/analyses", headers={**headers, "Origin": "https://unlisted.example"})
        assert response.status_code == 400
        assert "access-control-allow-origin" not in response.headers
