-- Additive Scenario C run support; all existing sealed evidence remains immutable.
ALTER TABLE railplan.ps1_optimisation_runs
  DROP CONSTRAINT ps1_optimisation_runs_scenario_check,
  ADD CONSTRAINT ps1_optimisation_runs_scenario_check CHECK(scenario IN ('A','B','C'));
