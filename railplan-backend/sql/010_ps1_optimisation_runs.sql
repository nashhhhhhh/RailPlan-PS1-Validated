-- Terminal-only history, separate from legacy nightly optimisation_runs.
CREATE TABLE railplan.ps1_optimisation_runs (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 instance_id uuid NOT NULL,
 operator_id uuid NOT NULL REFERENCES railplan.operators(id) ON DELETE RESTRICT,
 created_by uuid NOT NULL REFERENCES railplan.users(id) ON DELETE RESTRICT,
 baseline_run_id uuid,
 scenario text NOT NULL CHECK(scenario='A'),
 solver_status text NOT NULL CHECK(solver_status IN ('OPTIMAL','FEASIBLE','INFEASIBLE','UNKNOWN','MODEL_LIMIT','VALIDATION_FAILED','ERROR','MODEL_INVALID')),
 terminal_outcome text NOT NULL,
 optimiser_version text NOT NULL,
 validator_version text NOT NULL,
 policy_version text NOT NULL,
 dataset_fingerprint text NOT NULL CHECK(length(dataset_fingerprint)=64),
 input_fingerprint text NOT NULL CHECK(length(input_fingerprint)=64),
 request_snapshot jsonb NOT NULL,
 solver_configuration jsonb NOT NULL,
 result_snapshot jsonb NOT NULL,
 validation_snapshot jsonb,
 diagnostics jsonb NOT NULL,
 primary_optimal boolean NOT NULL,
 lexicographic_complete boolean NOT NULL,
 physical_validation_complete boolean NOT NULL,
 publishable boolean NOT NULL,
 objective_score numeric,
 primary_objective_bound numeric,
 primary_objective_gap numeric,
 solve_duration_seconds double precision NOT NULL CHECK(solve_duration_seconds>=0 AND solve_duration_seconds<'Infinity'::double precision),
 started_at timestamptz NOT NULL,
 completed_at timestamptz NOT NULL CHECK(completed_at>=started_at),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 accepted_csvs jsonb,
 schedule_snapshot jsonb NOT NULL,
 creation_txid bigint NOT NULL DEFAULT txid_current(),
 FOREIGN KEY(instance_id,operator_id) REFERENCES railplan.ps1_instances(id,operator_id) ON DELETE RESTRICT,
 UNIQUE(id,instance_id,operator_id),
 UNIQUE(id,instance_id,operator_id,input_fingerprint),
 FOREIGN KEY(baseline_run_id,instance_id,operator_id) REFERENCES railplan.ps1_optimisation_runs(id,instance_id,operator_id) ON DELETE RESTRICT,
 CHECK(terminal_outcome=CASE solver_status WHEN 'UNKNOWN' THEN 'bounded' ELSE lower(solver_status) END),
 CHECK(NOT publishable OR (solver_status IN ('OPTIMAL','FEASIBLE') AND physical_validation_complete AND accepted_csvs IS NOT NULL AND objective_score IS NOT NULL)),
 CHECK(publishable OR (accepted_csvs IS NULL AND objective_score IS NULL)),
 CHECK(NOT lexicographic_complete OR primary_optimal),
 CHECK(result_snapshot->>'judge_validation'='not_run' AND result_snapshot->>'score_verification'='internal_only')
);
CREATE INDEX ps1_optimisation_history ON railplan.ps1_optimisation_runs(operator_id,instance_id,created_at DESC,id DESC);
CREATE INDEX ps1_optimisation_baseline ON railplan.ps1_optimisation_runs(baseline_run_id);
CREATE TABLE railplan.ps1_optimisation_accesses (
 run_id uuid NOT NULL,
 instance_id uuid NOT NULL,
 operator_id uuid NOT NULL,
 activity_id text NOT NULL,
 access_seq integer NOT NULL CHECK(access_seq>0),
 week integer NOT NULL CHECK(week>0),
 physical_night integer NOT NULL CHECK(physical_night BETWEEN 1 AND 7),
 access_night integer NOT NULL CHECK(access_night>0),
 eclo integer NOT NULL CHECK(eclo=0),
 locked boolean NOT NULL,
 baseline_week integer CHECK(baseline_week>0),
 baseline_physical_night integer CHECK(baseline_physical_night BETWEEN 1 AND 7),
 PRIMARY KEY(run_id,activity_id,access_seq),
 UNIQUE(run_id,activity_id,week),
 FOREIGN KEY(run_id,instance_id,operator_id) REFERENCES railplan.ps1_optimisation_runs(id,instance_id,operator_id) ON DELETE RESTRICT
);
CREATE INDEX ps1_opt_access_week ON railplan.ps1_optimisation_accesses(run_id,week,activity_id,access_seq);
CREATE TABLE railplan.ps1_optimisation_occupancies (
 run_id uuid NOT NULL,
 instance_id uuid NOT NULL,
 operator_id uuid NOT NULL,
 activity_id text NOT NULL,
 week integer NOT NULL,
 location_id text NOT NULL,
 co_share_group text NOT NULL,
 PRIMARY KEY(run_id,activity_id,week,location_id),
 FOREIGN KEY(run_id,instance_id,operator_id) REFERENCES railplan.ps1_optimisation_runs(id,instance_id,operator_id) ON DELETE RESTRICT,
 FOREIGN KEY(run_id,activity_id,week) REFERENCES railplan.ps1_optimisation_accesses(run_id,activity_id,week) ON DELETE RESTRICT
);
CREATE INDEX ps1_opt_occupancy_week ON railplan.ps1_optimisation_occupancies(run_id,week,location_id,activity_id);
CREATE TABLE railplan.ps1_optimisation_contract_results (
 run_id uuid NOT NULL,
 instance_id uuid NOT NULL,
 operator_id uuid NOT NULL,
 contract_number text NOT NULL,
 simulated_completion_date date NOT NULL,
 overrun_days integer NOT NULL CHECK(overrun_days>=0),
 weighted_overrun numeric,
 PRIMARY KEY(run_id,contract_number),
 FOREIGN KEY(run_id,instance_id,operator_id) REFERENCES railplan.ps1_optimisation_runs(id,instance_id,operator_id) ON DELETE RESTRICT
);
CREATE TABLE railplan.ps1_optimisation_keys (
 operator_id uuid NOT NULL,
 instance_id uuid NOT NULL,
 idempotency_key text NOT NULL CHECK(length(idempotency_key) BETWEEN 1 AND 128 AND idempotency_key !~ '[[:space:]]'),
 input_fingerprint text NOT NULL,
 run_id uuid NOT NULL,
 PRIMARY KEY(operator_id,instance_id,idempotency_key),
 FOREIGN KEY(run_id,instance_id,operator_id,input_fingerprint) REFERENCES railplan.ps1_optimisation_runs(id,instance_id,operator_id,input_fingerprint) ON DELETE RESTRICT
);

CREATE INDEX ps1_opt_keys_run ON railplan.ps1_optimisation_keys(run_id);

CREATE FUNCTION railplan.ps1_opt_stamp() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 NEW.creation_txid=txid_current(); -- Never accept a caller-selected sealing transaction.
 IF NOT EXISTS(SELECT 1 FROM railplan.users u JOIN railplan.departments d ON d.id=u.department_id WHERE u.id=NEW.created_by AND d.operator_id=NEW.operator_id) THEN
  RAISE EXCEPTION 'Optimisation creator must belong to the instance operator';
 END IF;
 IF NEW.baseline_run_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM railplan.ps1_optimisation_runs r WHERE r.id=NEW.baseline_run_id AND r.instance_id=NEW.instance_id AND r.operator_id=NEW.operator_id AND r.publishable) THEN
  RAISE EXCEPTION 'Baseline must be an accepted run of the same instance/operator';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER stamp_insert BEFORE INSERT ON railplan.ps1_optimisation_runs FOR EACH ROW EXECUTE FUNCTION railplan.ps1_opt_stamp();

CREATE FUNCTION railplan.ps1_opt_child_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE parent railplan.ps1_optimisation_runs; field text; doc jsonb;
BEGIN
 SELECT * INTO STRICT parent FROM railplan.ps1_optimisation_runs WHERE id=NEW.run_id;
 IF parent.creation_txid<>txid_current() THEN RAISE EXCEPTION 'Optimisation result is sealed'; END IF;
 IF TG_TABLE_NAME<>'ps1_optimisation_keys' AND NOT parent.publishable THEN
  RAISE EXCEPTION 'Diagnostic run cannot contain accepted schedule rows';
 END IF;
 IF TG_TABLE_NAME='ps1_optimisation_keys' THEN
  IF NEW.idempotency_key IS DISTINCT FROM parent.request_snapshot->>'idempotency_key' THEN
   RAISE EXCEPTION 'Key association must match the original request';
  END IF;
 ELSE
  field=replace(TG_TABLE_NAME,'ps1_optimisation_','');
  doc=to_jsonb(NEW)-'run_id'-'instance_id'-'operator_id';
  IF NOT COALESCE((parent.schedule_snapshot->field) @> jsonb_build_array(doc),false) THEN
   RAISE EXCEPTION 'Child content is not in the canonical manifest';
  END IF;
 END IF;
 RETURN NEW;
END $$;

-- Deferred at commit: missing, extra or altered child content aborts the whole result.
-- Scheduling rows are duplicated in a canonical manifest specifically to enforce sealing.
CREATE FUNCTION railplan.ps1_opt_seal() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE actual jsonb; expected jsonb; relation text; field text;
BEGIN
 IF NEW.result_snapshot->>'solver_status' IS DISTINCT FROM NEW.solver_status
    OR (NEW.result_snapshot->>'publishable')::boolean IS DISTINCT FROM NEW.publishable
    OR (NEW.result_snapshot->>'primary_optimal')::boolean IS DISTINCT FROM NEW.primary_optimal
    OR (NEW.result_snapshot->>'lexicographic_complete')::boolean IS DISTINCT FROM NEW.lexicographic_complete
    OR (NEW.result_snapshot->>'physical_validation_complete')::boolean IS DISTINCT FROM NEW.physical_validation_complete THEN
  RAISE EXCEPTION 'Terminal metadata must match its immutable result snapshot';
 END IF;
 IF NEW.publishable THEN
  IF NOT COALESCE((NEW.validation_snapshot->>'feasible')::boolean,false)
     OR NOT COALESCE((NEW.validation_snapshot->>'physical_validation_complete')::boolean,false)
     OR NEW.validation_snapshot->'hard_violations' IS DISTINCT FROM '[]'::jsonb
     OR NEW.accepted_csvs IS DISTINCT FROM NEW.result_snapshot->'submission_files'
     OR NEW.result_snapshot->'validation_report' IS DISTINCT FROM NEW.validation_snapshot
     OR (NEW.validation_snapshot->>'objective_score')::numeric IS DISTINCT FROM NEW.objective_score
     OR NOT COALESCE((NEW.result_snapshot->>'publishable')::boolean,false) THEN
   RAISE EXCEPTION 'Accepted result must retain its complete rich validation and exact CSVs';
  END IF;
 END IF;
 FOREACH field IN ARRAY ARRAY['accesses','occupancies','contract_results'] LOOP
  relation='ps1_optimisation_'||field;
  expected=NEW.schedule_snapshot->field;
  IF expected IS NULL OR jsonb_typeof(expected)<>'array' THEN RAISE EXCEPTION 'Missing canonical schedule manifest'; END IF;
  EXECUTE format('SELECT COALESCE(jsonb_agg(to_jsonb(c)-''run_id''-''instance_id''-''operator_id''),''[]''::jsonb) FROM railplan.%I c WHERE run_id=$1',relation) INTO actual USING NEW.id;
  IF (SELECT count(*) FROM jsonb_array_elements(actual))<>(SELECT count(*) FROM jsonb_array_elements(expected))
     OR EXISTS(SELECT value FROM jsonb_array_elements(actual) EXCEPT SELECT value FROM jsonb_array_elements(expected))
     OR EXISTS(SELECT value FROM jsonb_array_elements(expected) EXCEPT SELECT value FROM jsonb_array_elements(actual)) THEN
   RAISE EXCEPTION 'Incomplete or inconsistent sealed %',relation;
  END IF;
  IF NOT NEW.publishable AND expected<>'[]'::jsonb THEN RAISE EXCEPTION 'Rejected result has accepted schedule manifest'; END IF;
 END LOOP;
 IF NEW.request_snapshot->>'idempotency_key' IS NOT NULL AND
    NOT EXISTS(SELECT 1 FROM railplan.ps1_optimisation_keys WHERE run_id=NEW.id AND idempotency_key=NEW.request_snapshot->>'idempotency_key') THEN
  RAISE EXCEPTION 'Missing terminal idempotency association';
 END IF;
 RETURN NEW;
END $$;
CREATE CONSTRAINT TRIGGER seal_result AFTER INSERT ON railplan.ps1_optimisation_runs DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION railplan.ps1_opt_seal();

CREATE FUNCTION railplan.ps1_opt_audit() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE doc jsonb;
BEGIN
 doc=to_jsonb(NEW);
 INSERT INTO railplan.audit_logs(actor_id,action,entity_type,entity_id,after_state,correlation_id,source)
 VALUES(NULLIF(current_setting('railplan.actor_id',true),'')::uuid,'INSERT',TG_TABLE_NAME,
 COALESCE(doc->>'id',doc->>'run_id')::uuid,doc,NULLIF(current_setting('railplan.correlation_id',true),'')::uuid,
 COALESCE(NULLIF(current_setting('railplan.source',true),''),'database'));
 RETURN NEW;
END $$;
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['ps1_optimisation_runs','ps1_optimisation_accesses','ps1_optimisation_occupancies','ps1_optimisation_contract_results','ps1_optimisation_keys'] LOOP
  EXECUTE format('CREATE TRIGGER immutable_row BEFORE UPDATE OR DELETE ON railplan.%I FOR EACH ROW EXECUTE FUNCTION railplan.deny_mutation()',t);
  EXECUTE format('CREATE TRIGGER immutable_table BEFORE TRUNCATE ON railplan.%I FOR EACH STATEMENT EXECUTE FUNCTION railplan.deny_mutation()',t);
  EXECUTE format('CREATE TRIGGER audit_insert AFTER INSERT ON railplan.%I FOR EACH ROW EXECUTE FUNCTION railplan.ps1_opt_audit()',t);
  IF t<>'ps1_optimisation_runs' THEN
   EXECUTE format('CREATE TRIGGER sealed_parent BEFORE INSERT ON railplan.%I FOR EACH ROW EXECUTE FUNCTION railplan.ps1_opt_child_guard()',t);
  END IF;
 END LOOP;
END $$;
