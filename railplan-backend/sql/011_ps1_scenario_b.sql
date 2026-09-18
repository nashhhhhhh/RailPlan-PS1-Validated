-- Additive Scenario B support; existing Scenario A history remains immutable.
ALTER TABLE railplan.ps1_optimisation_runs
  DROP CONSTRAINT ps1_optimisation_runs_scenario_check,
  ADD CONSTRAINT ps1_optimisation_runs_scenario_check CHECK(scenario IN ('A','B'));

ALTER TABLE railplan.ps1_optimisation_accesses
  DROP CONSTRAINT ps1_optimisation_accesses_eclo_check,
  ADD CONSTRAINT ps1_optimisation_accesses_eclo_check CHECK(eclo IN (0,1));
