from copy import deepcopy
from decimal import Decimal
import importlib
import pytest
from pydantic import ValidationError
from pglast import parse_sql
from app.scoring import PolicyCreate, ScoreCreate, evaluate, band, overlap_score, fingerprint, rounded

def sample():
    return {"conflict":{"severity":"critical","detection_method":"synthetic"},
      "rule":{"severity":"critical","code":"ISO","version":1,"blocking":True,"authority_reference":"Synthetic example"},
      "requests":[{"priority":"urgent","requested_start":"2026-09-14T01:00:00+08:00","requested_end":"2026-09-14T02:00:00+08:00"},
                  {"priority":"normal","requested_start":"2026-09-14T01:30:00+08:00","requested_end":"2026-09-14T03:00:00+08:00"}],
      "equipment":[]}

@pytest.mark.parametrize("value,expected",[(0,"information"),(19.99,"information"),(20,"low"),(39.99,"low"),(40,"medium"),(60,"high"),(80,"critical"),(100,"critical")])
def test_bands(value,expected): assert band(str(value))==expected

@pytest.mark.parametrize("value",[-1,101,"NaN","Infinity"])
def test_band_bounds(value):
    with pytest.raises(ValueError):band(value)

@pytest.mark.parametrize("minutes,expected",[(0,0),(.1,20),(15,20),(15.1,40),(30,40),(30.1,65),(60,65),(60.1,85),(120,85),(120.1,100)])
def test_overlap_buckets(minutes,expected):assert overlap_score(minutes)==expected

@pytest.mark.parametrize("weights",[{}, {"safety":1},dict(safety=.4,operational=.25,resource=.2,urgency=.1,passenger=.1),dict(safety=-.1,operational=.5,resource=.4,urgency=.1,passenger=.1),dict(safety="NaN",operational=0,resource=0,urgency=0,passenger=0)])
def test_policy_rejects_invalid_weights(weights):
    with pytest.raises(ValidationError):PolicyCreate(weights=weights)

def test_partial_fixed_denominator_and_safety_floor():
    r=evaluate(sample(),PolicyCreate())
    assert r.risk_score==54 # 100*.35 + 40*.25 + 90*.10
    assert r.risk_upper_bound==84
    assert r.coverage==.7 and r.confidence==.18
    assert r.effective_severity=="critical" and r.blocking
    assert r.score_status=="partial" and not r.eligible_for_auto_prioritisation
    unknown=[c for c in r.components if c.score is None]
    assert [c.name for c in unknown]==["resource","passenger"]
    assert all(c.weighted_contribution is None and c.missing_inputs for c in unknown)

def test_confidence_does_not_scale_risk():
    s=sample(); first=evaluate(s,PolicyCreate())
    s["conflict"]["detection_method"]="automatic";s["rule"]["authority_reference"]="Reference"
    second=evaluate(s,PolicyCreate())
    assert first.risk_score==second.risk_score
    assert first.confidence<second.confidence
    assert second.score_status=="partial" and not second.policy_validated

def test_blocking_is_independent():
    s=sample();s["rule"]["blocking"]=False
    assert not evaluate(s,PolicyCreate()).blocking

def test_legacy_severity_never_downgraded():
    s=sample();s["rule"]["severity"]="low"
    assert evaluate(s,PolicyCreate()).effective_severity=="critical"

def test_missing_requests_and_unknown_weight():
    s=sample();s["requests"]=[]
    r=evaluate(s,PolicyCreate(weights=dict(safety=0,operational=0,resource=0,urgency=0,passenger=1)))
    assert r.risk_score is None and r.score_status=="unknown" and r.confidence==0
    assert r.effective_severity=="critical" and r.blocking

def test_invalid_intervals_do_not_become_zero():
    s=sample();s["requests"][0]["requested_end"]="invalid"
    assert evaluate(s,PolicyCreate()).components[1].score is None

def test_adjacent_intervals_are_zero():
    s=sample();s["requests"][1]["requested_start"]="2026-09-14T02:00:00+08:00"
    assert evaluate(s,PolicyCreate()).components[1].score==0

def test_scenario_intervals_override_requested_intervals():
    s=sample();s["scenario"]={"id":"scenario"};s["assignments"]=[]
    assert evaluate(s,PolicyCreate()).components[1].score is None

def test_decimal_rounding_and_stable_hash():
    assert rounded(Decimal("19.995"))==20
    assert fingerprint({"a":1,"b":2})==fingerprint({"b":2,"a":1})
    assert fingerprint({"a":1})!=fingerprint({"a":2})

def test_physical_asset_double_booking_requires_overlap():
    s=sample()
    for i,r in enumerate(s["requests"]):r["id"]=str(i)
    s["allocations"]=[{"request_id":str(i),"kind":"asset","resource_id":"asset-1"} for i in range(2)]
    assert evaluate(s,PolicyCreate()).components[2].score==80
    s["requests"][1]["requested_start"]="2026-09-14T02:00:00+08:00"
    assert evaluate(s,PolicyCreate()).components[2].score is None

def test_distinct_physical_assets_are_not_a_type_shortage():
    s=sample()
    for i,r in enumerate(s["requests"]):r["id"]=str(i)
    s["allocations"]=[{"request_id":str(i),"kind":"asset","resource_id":str(i)} for i in range(2)]
    assert evaluate(s,PolicyCreate()).components[2].score is None

def test_scoring_migration_parses(monkeypatch):
    migration=importlib.import_module("migrations.versions.0003_conflict_scoring")
    class Connection:
        def exec_driver_sql(self,sql,**kwargs):
            assert parse_sql(sql)
            assert kwargs["execution_options"]["no_parameters"]
    monkeypatch.setattr(migration.op,"get_bind",lambda:Connection())
    migration.upgrade()
    with pytest.raises(RuntimeError):migration.downgrade()
