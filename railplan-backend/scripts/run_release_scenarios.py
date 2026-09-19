"""Exercise optimiser modules against the bundled organiser instance.

The runner never converts an unavailable, unknown, infeasible or invalid result
into submission CSVs. Scenario availability is reported from the authoritative
source tree so a release cannot silently substitute sample schedules.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import monotonic

from app.ps1 import load_files, parse_instance
from app.ps1_optimisation.contracts import OptimiseInput, ScenarioBOptimiseInput, ScenarioCOptimiseInput
from app.ps1_optimisation.service import optimise, optimise_scenario_b, optimise_scenario_c


ROOT = Path(__file__).resolve().parents[1]


def diagnostic_summary(items: list[dict]) -> list[dict]:
    summary = []
    for item in items:
        if item.get("code") == "physical_pair_constraints":
            summary.append({
                "code": item["code"],
                "incompatible_pair_count": len(item.get("incompatible_pairs", [])),
            })
        else:
            summary.append(item)
    return summary


def run_scenario(scenario: str, seconds: float, deterministic_seconds: float, seed: int, candidate_dir: Path | None) -> dict:
    dataset = parse_instance(load_files())
    option_type = {"A": OptimiseInput, "B": ScenarioBOptimiseInput, "C": ScenarioCOptimiseInput}[scenario]
    solver = {"A": optimise, "B": optimise_scenario_b, "C": optimise_scenario_c}[scenario]
    options = option_type(
        time_limit_seconds=seconds,
        deterministic_time_limit=deterministic_seconds,
        random_seed=seed,
    )
    started = monotonic()
    result = solver(dataset, options)
    elapsed = monotonic() - started
    primary_name = {"A": "weighted_overrun_scaled_10", "B": "official_scenario_b_objective", "C": "official_scenario_c_objective_scaled_10"}[scenario]
    primary = next((stage for stage in result.stages if stage.get("name") == primary_name), {})
    validation = result.validation_report
    if candidate_dir is not None and result.publishable:
        destination = candidate_dir / f"scenario-{scenario.lower()}"
        destination.mkdir(parents=True, exist_ok=False)
        for name, content in (result.submission_files or {}).items():
            (destination / name).write_text(content, encoding="utf-8", newline="")
    return {
        "available": True,
        "execution_status": "COMPLETED",
        "solver_status": result.solver_status,
        "elapsed_seconds": round(elapsed, 6),
        "solver_elapsed_seconds": round(result.solve_time_seconds, 6),
        "configured_wall_limit_seconds": seconds,
        "configured_deterministic_limit": deterministic_seconds,
        "deterministic_seed": seed,
        "objective_stage": primary.get("name"),
        "objective_bound": primary.get("best_bound"),
        "objective_value": primary.get("value"),
        "objective_score": validation.objective_score if validation else None,
        "publishable": result.publishable,
        "physical_validation_status": (
            validation.validation_status if validation and validation.physical_validation_complete else "not_complete"
        ),
        "physical_validation_complete": result.physical_validation_complete,
        "validator_violations": [item.model_dump(mode="json") for item in validation.hard_violations] if validation else [],
        "diagnostics": diagnostic_summary(result.diagnostics),
        "csv_files_written": sorted(result.submission_files) if result.publishable and candidate_dir is not None else [],
        "judge_validation": result.judge_validation,
        "score_verification": result.score_verification,
    }
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--a-seconds", type=float, default=20.0)
    parser.add_argument("--b-seconds", type=float, default=20.0)
    parser.add_argument("--c-seconds", type=float, default=20.0)
    parser.add_argument("--deterministic-seconds", type=float, default=10.0)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--candidate-dir", type=Path)
    args = parser.parse_args()
    for name, value in (("A", args.a_seconds), ("B", args.b_seconds), ("C", args.c_seconds)):
        if not 0.1 <= value <= 120:
            parser.error(f"Scenario {name} time limit must be in 0.1..120 seconds")
    if not 0.001 <= args.deterministic_seconds <= 60:
        parser.error("deterministic limit must be in 0.001..60")
    if args.output.exists():
        parser.error("output already exists")
    if args.candidate_dir is not None and args.candidate_dir.exists():
        parser.error("candidate directory already exists")

    scenarios = {
        "A": run_scenario("A", args.a_seconds, args.deterministic_seconds, args.seed, args.candidate_dir),
        "B": run_scenario("B", args.b_seconds, args.deterministic_seconds, args.seed, args.candidate_dir),
        "C": run_scenario("C", args.c_seconds, args.deterministic_seconds, args.seed, args.candidate_dir),
    }
    report = {
        "dataset": "bundled organiser PS1 input (eight files under data/PS1/01_data)",
        "dataset_fingerprint": parse_instance(load_files())["fingerprint"],
        "scenario_results": scenarios,
        "notes": [
            "Organiser submission samples are reference inputs to validation and are never treated as RailPlan-generated candidates.",
            "Only rich-validator-accepted candidates may be written.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report["scenario_results"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
