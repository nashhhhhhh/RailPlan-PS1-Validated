# Scenario C optimiser release

Scenario C is implemented as a bounded, deterministic Google OR-Tools CP-SAT solve. It shares the elastic access/workload and possession machinery introduced for Scenario B while keeping the Scenario C deadline, capacity, line-window and objective rules explicit.

## Behaviour

- Workload scale: normal access 2, ECLO 3, required work `2 × total_accesses`; sufficient work is mandatory and avoidable over-delivery is a secondary objective.
- Delay: activity completion uses the validator's Sunday week-to-date conversion. Scale-10 weighted overrun uses contract tier weights 100/10/1 and activity multipliers 13/12/10.
- Capacity: each canonical location/week may use at most one possession group above supply. Excess is summed and penalised.
- ECLO windows: Alpha and Beta independently use zero, one or two consecutive calendar weeks. Cross-line ECLO accesses participate in both windows.
- Primary objective: `priority-weighted overrun + 7 × excess access nights + 5 × ECLO nights`; the model uses the exact integer equivalent `weighted_scaled_10 + 70 × excess + 50 × ECLO`.
- Safety: physical-night conflicts use canonical closure footprints. Physical night, contract-local access night and location/week co-share group remain separate identities.
- Publication: three organiser CSVs are exposed only after complete rich validation. Judge validation is not run and score verification remains internal only.

## Interfaces and persistence

- Saved: `POST /api/ps1/instances/{instance_id}/optimise/scenario-c`
- Stateless: `POST /api/ps1/optimise/scenario-c/preview`
- Filtered history: `GET /api/ps1/instances/{instance_id}/optimisations?scenario=C`
- Database head: Alembic `0011`; migration `0009` permits C in the existing sealed run table.
- Versions: optimiser `ps1-optimiser/1.2.0`, validator `ps1-validator/1.1.0`, policy `ps1-policy/4-scenario-c-line-windows`.

The UI enables Scenario C in saved and local-preview modes, shows objective components, workload, line windows, cross-line activities, hotspots and rejected-candidate evidence, and provides a focused latest-run A/B/C comparison. Objective values from unlike scenarios are explicitly not directly ranked.

## Search and organiser baseline evidence

Scenario C now starts with a hard-constraint feasibility stage, promotes the complete accepted assignment to a CP-SAT hint, and then runs the unchanged exact objective and deterministic secondary stages. Equivalent physical-conflict encoding uses one guarded physical-night inequality per incompatible pair/week instead of seven per-night clauses. This reduces presolve size without removing a feasible assignment.

The exact organiser Scenario A candidate was explicitly converted and checked as C, but failed C validation on physical buffer conflicts. It is therefore not used as a fallback. A Scenario B candidate is used only as a repairable search hint; Scenario C still finds and validates its own unrestricted candidate. Current generated evidence, solver telemetry, bounds and provenance are stored in `competition-submission/evidence/scenario-c.json`. `FEASIBLE` is not reported as `OPTIMAL`.

RailPlan-generated public outputs are produced with:

```bash
cd railplan-backend
python -m scripts.generate_public_test_results --output ../competition-submission \
  --scenarios A B C --seed 0 --time-limit-seconds 120 --deterministic-limit 60
```

The generator refuses overwrite unless `--overwrite` is explicit, re-imports every candidate, compares objective components, writes no files for rejected/unknown scenarios, and supports `--allow-partial` for an honestly incomplete A/B-only release.

## Provisional policy assumptions

The source package has no dated engineering-night calendar. The model therefore retains the configurable uniform 1–7 network-wide physical-night domain per week. Completion dates use the validator's documented Sunday conversion. Canonical closure-footprint line membership determines whether an ECLO access affects Alpha, Beta or both. These assumptions are persisted with every run; they are not claims of official-judge compatibility.
