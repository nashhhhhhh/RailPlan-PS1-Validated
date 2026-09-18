-- Immutable internal PS1 validation evidence, separate from legacy conflicts.
ALTER TABLE railplan.ps1_instances ADD CONSTRAINT ps1_instance_operator_key UNIQUE(id,operator_id);
CREATE TABLE railplan.ps1_validation_runs (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 instance_id uuid NOT NULL,
 operator_id uuid NOT NULL REFERENCES railplan.operators(id) ON DELETE RESTRICT,
 created_by uuid NOT NULL REFERENCES railplan.users(id) ON DELETE RESTRICT,
 scenario text NOT NULL CHECK(scenario IN ('A','B','C')),
 dataset_fingerprint text NOT NULL CHECK(length(dataset_fingerprint)=64),
 submission_fingerprint text NOT NULL CHECK(length(submission_fingerprint)=64),
 validator_version text NOT NULL,
 source_files jsonb NOT NULL,
 policy_snapshot jsonb NOT NULL,
 result_snapshot jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(instance_id,operator_id) REFERENCES railplan.ps1_instances(id,operator_id) ON DELETE RESTRICT,
 UNIQUE(instance_id,submission_fingerprint,validator_version),
 UNIQUE(id,operator_id)
);
CREATE INDEX ps1_validation_history ON railplan.ps1_validation_runs(operator_id,instance_id,created_at DESC,id);
CREATE TABLE railplan.ps1_validation_violations (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 validation_id uuid NOT NULL,
 operator_id uuid NOT NULL REFERENCES railplan.operators(id) ON DELETE RESTRICT,
 ordinal integer NOT NULL CHECK(ordinal>=0),
 rule_code text NOT NULL,
 evidence_snapshot jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(validation_id,operator_id) REFERENCES railplan.ps1_validation_runs(id,operator_id) ON DELETE RESTRICT,
 UNIQUE(validation_id,ordinal)
);
CREATE INDEX ps1_violations_rule ON railplan.ps1_validation_violations(validation_id,rule_code,ordinal);
CREATE TABLE railplan.ps1_validation_keys (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 operator_id uuid NOT NULL REFERENCES railplan.operators(id) ON DELETE RESTRICT,
 idempotency_key text NOT NULL CHECK(length(idempotency_key) BETWEEN 1 AND 128),
 request_fingerprint text NOT NULL CHECK(length(request_fingerprint)=64),
 validation_id uuid NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(validation_id,operator_id) REFERENCES railplan.ps1_validation_runs(id,operator_id) ON DELETE RESTRICT,
 UNIQUE(operator_id,idempotency_key)
);
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['ps1_validation_runs','ps1_validation_violations','ps1_validation_keys'] LOOP
  EXECUTE format('CREATE TRIGGER immutable_row BEFORE UPDATE OR DELETE ON railplan.%I FOR EACH ROW EXECUTE FUNCTION railplan.deny_mutation()',t);
  EXECUTE format('CREATE TRIGGER immutable_table BEFORE TRUNCATE ON railplan.%I FOR EACH STATEMENT EXECUTE FUNCTION railplan.deny_mutation()',t);
  EXECUTE format('CREATE TRIGGER audit_insert AFTER INSERT ON railplan.%I FOR EACH ROW EXECUTE FUNCTION railplan.audit_change()',t);
 END LOOP;
END $$;
