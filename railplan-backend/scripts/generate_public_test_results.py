"""Generate validator-approved RailPlan outputs for the bundled public PS1 data."""
from __future__ import annotations

import argparse
import csv
from hashlib import sha256
import io
import json
from pathlib import Path
import shutil

from app.ps1 import load_files, parse_instance
from app.ps1_optimisation.contracts import (
    VERSION as OPTIMISER_VERSION,
    OptimiseInput,
    ScenarioBOptimiseInput,
    ScenarioCOptimiseInput,
)
from app.ps1_optimisation.service import optimise, optimise_scenario_b, optimise_scenario_c
from app.ps1_validation.service import validate


ROOT = Path(__file__).resolve().parents[2]
HEADERS = {
    "SCHEDULE_ACCESS.csv": ["activity_id", "access_seq", "week", "eclo", "access_night"],
    "SCHEDULE_OCCUPANCY.csv": ["activity_id", "week", "location_id", "co_share_group"],
    "RESULTS.csv": ["scenario", "contract_number", "simulated_completion_date", "overrun_days"],
}


def _rows(content: str, name: str) -> list[dict[str, str]]:
    if "\r" in content or not content.endswith("\n"):
        raise RuntimeError(f"{name} must use UTF-8 LF and end with a newline")
    reader = csv.DictReader(io.StringIO(content))
    if reader.fieldnames != HEADERS[name]:
        raise RuntimeError(f"Unexpected {name} header: {reader.fieldnames}")
    return list(reader)


def _verify_order(files: dict[str, str], scenario: str) -> None:
    access = _rows(files["SCHEDULE_ACCESS.csv"], "SCHEDULE_ACCESS.csv")
    occupancy = _rows(files["SCHEDULE_OCCUPANCY.csv"], "SCHEDULE_OCCUPANCY.csv")
    results = _rows(files["RESULTS.csv"], "RESULTS.csv")
    if access != sorted(access, key=lambda row: (row["activity_id"], int(row["access_seq"]))):
        raise RuntimeError("SCHEDULE_ACCESS.csv is not stably ordered")
    if occupancy != sorted(occupancy, key=lambda row: (row["activity_id"], int(row["week"]), row["location_id"])):
        raise RuntimeError("SCHEDULE_OCCUPANCY.csv is not stably ordered")
    if results != sorted(results, key=lambda row: row["contract_number"]):
        raise RuntimeError("RESULTS.csv is not stably ordered")
    if any(row["scenario"] != scenario for row in results):
        raise RuntimeError("RESULTS.csv scenario does not match its output directory")
    if any("physical_night" in header for header in HEADERS.values() for header in header):
        raise AssertionError("Internal physical nights must not be exported")
    if scenario == "A" and any(row["eclo"] != "0" for row in access):
        raise RuntimeError("Scenario A output contains ECLO")


def _primary(result, scenario: str) -> dict:
    name = {"A": "weighted_overrun_scaled_10", "B": "official_scenario_b_objective", "C": "official_scenario_c_objective_scaled_10"}[scenario]
    return next((stage for stage in result.stages if stage.get("name") == name), {})


def _evidence(dataset: dict, result, scenario: str, seed: int, wall: float, deterministic: float, report: dict) -> dict:
    physical = [row.model_dump(mode="json") for row in result.physical_nights]
    physical_bytes = (json.dumps(physical, sort_keys=True, separators=(",", ":")) + "\n").encode()
    primary = _primary(result, scenario)
    return {
        "scenario": scenario,
        "dataset_fingerprint": dataset["fingerprint"],
        "submission_fingerprint": report["submission_fingerprint"],
        "solver_version": OPTIMISER_VERSION,
        "validator_version": report["validator_version"],
        "policy_version": report["rule_policy"]["version"],
        "seed": seed,
        "time_limit_seconds": wall,
        "deterministic_limit": deterministic,
        "solver_status": result.solver_status,
        "candidate_source": result.candidate_source,
        "optimality_proven": result.optimality_proven,
        "solve_time_seconds": result.solve_time_seconds,
        "objective_value": report["objective_score"],
        "objective_bound": primary.get("best_bound"),
        "objective_components": report["objective_components"],
        "physical_validation_complete": report["physical_validation_complete"],
        "hard_violation_count": len(report["hard_violations"]),
        "publishable": result.publishable,
        "internal_physical_night_fingerprint": sha256(physical_bytes).hexdigest(),
        "judge_validation": "not_run",
        "score_verification": "internal_only",
        "stages": result.stages,
        "diagnostics": result.diagnostics,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scenarios", nargs="+", choices=("A", "B", "C"), default=["A", "B", "C"])
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--time-limit-seconds", type=float, default=120)
    parser.add_argument("--deterministic-limit", type=float, default=60)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--allow-partial", action="store_true", help="Keep accepted scenarios and report unavailable requested scenarios")
    args = parser.parse_args()
    output = args.output.resolve()
    if output == ROOT.resolve() or ROOT.resolve() not in output.parents:
        parser.error("output must be a dedicated directory below the repository root")
    if output.exists():
        if not args.overwrite:
            parser.error("output already exists; pass --overwrite to replace that directory")
        shutil.rmtree(output)
    output.mkdir(parents=True)
    evidence_dir = output / "evidence"
    evidence_dir.mkdir()

    dataset = parse_instance(load_files())
    solvers = {"A": (OptimiseInput, optimise), "B": (ScenarioBOptimiseInput, optimise_scenario_b), "C": (ScenarioCOptimiseInput, optimise_scenario_c)}
    results = {}
    failures = []
    baseline = []
    for scenario in args.scenarios:
        option_type, solver = solvers[scenario]
        extra = {"baseline_placements": baseline} if scenario == "C" and baseline else {}
        options = option_type(time_limit_seconds=args.time_limit_seconds,
            deterministic_time_limit=args.deterministic_limit, random_seed=args.seed, **extra)
        result = solver(dataset, options)
        if scenario == "B" and result.publishable:
            baseline = result.physical_nights
        if not result.publishable or not result.submission_files or not result.validation_report:
            failures.append(scenario)
            unavailable = {
                "scenario": scenario, "dataset_fingerprint": dataset["fingerprint"],
                "solver_status": result.solver_status, "candidate_source": result.candidate_source,
                "optimality_proven": False, "publishable": False,
                "physical_validation_complete": False, "hard_violation_count": None,
                "judge_validation": "not_run", "score_verification": "internal_only",
                "stages": result.stages, "diagnostics": result.diagnostics,
            }
            (evidence_dir / f"scenario-{scenario.lower()}.json").write_text(json.dumps(unavailable, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="")
            continue
        files = result.submission_files
        _verify_order(files, scenario)
        mapping = {(row.activity_id, row.week): row.physical_night for row in result.physical_nights}
        report = validate(dataset, files, scenario, physical_nights=mapping)
        original = result.validation_report.model_dump(mode="json")
        if not report["feasible"] or not report["physical_validation_complete"] or report["hard_violations"]:
            raise RuntimeError(f"Scenario {scenario} failed release revalidation")
        if report["objective_components"] != original["objective_components"]:
            raise RuntimeError(f"Scenario {scenario} objective changed during re-import")
        destination = output / f"scenario-{scenario.lower()}"
        destination.mkdir()
        for name in HEADERS:
            (destination / name).write_text(files[name], encoding="utf-8", newline="")
        evidence = _evidence(dataset, result, scenario, args.seed, args.time_limit_seconds, args.deterministic_limit, report)
        (evidence_dir / f"scenario-{scenario.lower()}.json").write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="")
        results[scenario] = evidence

    readme = """# RailPlan public test results

These submission files were generated by RailPlan from the bundled organiser input dataset and independently re-imported through the rich validator. They are not copies of the organiser sample outputs.

Validation is internal and provisional. Judge validation was not run, score verification is internal only, and conflict severity is separate from the schedule objective. Explicit physical-night assignments are recorded only by fingerprint in evidence; they are intentionally absent from organiser CSVs.
"""
    (output / "README.md").write_text(readme, encoding="utf-8", newline="")
    checksum_paths = sorted(path for path in output.rglob("*") if path.is_file() and path.name != "checksums.sha256")
    checksums = "".join(f"{sha256(path.read_bytes()).hexdigest()}  {path.relative_to(output).as_posix()}\n" for path in checksum_paths)
    (evidence_dir / "checksums.sha256").write_text(checksums, encoding="ascii", newline="")
    print(json.dumps({"output": str(args.output), "accepted": sorted(results), "unavailable": failures,
        "results": {key: {field: value[field] for field in ("solver_status", "candidate_source", "optimality_proven", "solve_time_seconds", "objective_value", "objective_bound", "submission_fingerprint")} for key, value in results.items()}}, indent=2))
    return 0 if not failures or args.allow_partial else 1


if __name__ == "__main__":
    raise SystemExit(main())
