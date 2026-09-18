-- PS1 retains its own weekly domain; never manufacture nightly MRT requests.
CREATE TABLE railplan.ps1_instances (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 operator_id uuid NOT NULL REFERENCES railplan.operators(id) ON DELETE RESTRICT,
 imported_by uuid NOT NULL REFERENCES railplan.users(id) ON DELETE RESTRICT,
 name text NOT NULL CHECK(length(name) BETWEEN 1 AND 120),
 fingerprint text NOT NULL CHECK(length(fingerprint)=64),
 format_version text NOT NULL,
 source_files jsonb NOT NULL,
 dataset jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(operator_id,fingerprint,format_version)
);
CREATE INDEX ps1_instances_operator_created ON railplan.ps1_instances(operator_id,created_at DESC,id);
CREATE TRIGGER ps1_instance_immutable BEFORE UPDATE OR DELETE ON railplan.ps1_instances
 FOR EACH ROW EXECUTE FUNCTION railplan.deny_mutation();
CREATE TRIGGER ps1_instance_no_truncate BEFORE TRUNCATE ON railplan.ps1_instances
 FOR EACH STATEMENT EXECUTE FUNCTION railplan.deny_mutation();
CREATE TRIGGER ps1_instance_audit AFTER INSERT ON railplan.ps1_instances
 FOR EACH ROW EXECUTE FUNCTION railplan.audit_change();
