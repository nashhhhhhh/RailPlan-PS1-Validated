-- Additive migration: legacy scores remain untouched.
ALTER TABLE railplan.conflicts ADD COLUMN version integer NOT NULL DEFAULT 1 CHECK(version>0);
ALTER TABLE railplan.scoring_policies ADD COLUMN operator_id uuid REFERENCES railplan.operators(id) ON DELETE RESTRICT;
ALTER TABLE railplan.scoring_policies ADD COLUMN definition jsonb;
ALTER TABLE railplan.scoring_policies DROP CONSTRAINT scoring_policies_code_version_key;
CREATE UNIQUE INDEX scoring_policy_operator_version ON railplan.scoring_policies(operator_id,code,version) NULLS NOT DISTINCT;

CREATE TABLE railplan.scoring_source_revision (
  id integer PRIMARY KEY CHECK(id=1),
  revision bigint NOT NULL DEFAULT 1
);
INSERT INTO railplan.scoring_source_revision(id) VALUES(1);

CREATE TABLE railplan.scoring_policy_activations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  operator_id uuid NOT NULL REFERENCES railplan.operators(id) ON DELETE RESTRICT,
  policy_id uuid NOT NULL REFERENCES railplan.scoring_policies(id) ON DELETE RESTRICT,
  activated_by uuid NOT NULL REFERENCES railplan.users(id) ON DELETE RESTRICT,
  starts_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  ends_at timestamptz,
  CHECK(ends_at IS NULL OR ends_at>=starts_at)
);
CREATE UNIQUE INDEX one_active_scoring_policy ON railplan.scoring_policy_activations(operator_id) WHERE ends_at IS NULL;

CREATE TABLE railplan.conflict_scores (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  conflict_id uuid NOT NULL REFERENCES railplan.conflicts(id) ON DELETE RESTRICT,
  policy_id uuid NOT NULL REFERENCES railplan.scoring_policies(id) ON DELETE RESTRICT,
  created_by uuid NOT NULL REFERENCES railplan.users(id) ON DELETE RESTRICT,
  source_revision bigint NOT NULL,
  input_fingerprint text NOT NULL,
  policy_fingerprint text NOT NULL,
  engine_version text NOT NULL,
  input_snapshot jsonb NOT NULL,
  policy_snapshot jsonb NOT NULL,
  result jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE(conflict_id,policy_id,input_fingerprint,policy_fingerprint,engine_version)
);
CREATE INDEX conflict_scores_latest ON railplan.conflict_scores(conflict_id,created_at DESC,id);
CREATE TABLE railplan.score_idempotency_keys (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  operator_id uuid NOT NULL REFERENCES railplan.operators(id) ON DELETE RESTRICT,
  key text NOT NULL,
  request_fingerprint text NOT NULL,
  score_id uuid NOT NULL REFERENCES railplan.conflict_scores(id) ON DELETE RESTRICT,
  UNIQUE(operator_id,key)
);
CREATE FUNCTION railplan.bump_scoring_revision() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 UPDATE railplan.scoring_source_revision SET revision=revision+1 WHERE id=1;
 RETURN NULL;
END $$;
CREATE FUNCTION railplan.bump_conflict_version() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN NEW.version=OLD.version+1; RETURN NEW; END $$;
CREATE TRIGGER scoring_conflict_version BEFORE UPDATE ON railplan.conflicts FOR EACH ROW EXECUTE FUNCTION railplan.bump_conflict_version();
-- Conservative database-wide invalidation. This reveals no other operator data.
-- Statement triggers also cover inserts, deletes, bulk edits, and truncation.
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['conflicts','conflict_requests','conflict_teams','conflict_engineers','conflict_equipment',
 'conflict_sectors','conflict_isolations','maintenance_requests','scenario_assignments','scenarios',
 'rule_definitions','analysis_runs','engineering_windows','scoring_policy_activations',
 'teams','engineers','equipment_assets','track_sectors','isolation_zones','window_periods',
 'team_memberships','shifts','workzone_sectors','isolation_zone_sectors','tracks','track_segments'] LOOP
 EXECUTE format('CREATE TRIGGER scoring_revision AFTER INSERT OR UPDATE OR DELETE OR TRUNCATE ON railplan.%I FOR EACH STATEMENT EXECUTE FUNCTION railplan.bump_scoring_revision()',t);
 END LOOP;
 -- Resource/requirement/link edits are also dependencies, even if not yet scored.
 FOR t IN SELECT tablename FROM pg_tables WHERE schemaname='railplan' AND
 (tablename LIKE '%availability%' OR tablename LIKE 'request_%' OR tablename LIKE 'scenario_%' OR tablename='engineer_skills')
 AND tablename <> 'scenario_assignments' LOOP
 EXECUTE format('CREATE TRIGGER scoring_revision AFTER INSERT OR UPDATE OR DELETE OR TRUNCATE ON railplan.%I FOR EACH STATEMENT EXECUTE FUNCTION railplan.bump_scoring_revision()',t);
 END LOOP;
END $$;
CREATE TRIGGER scoring_policy_immutable BEFORE UPDATE OR DELETE ON railplan.scoring_policies FOR EACH ROW EXECUTE FUNCTION railplan.deny_mutation();
CREATE TRIGGER scoring_policy_no_truncate BEFORE TRUNCATE ON railplan.scoring_policies FOR EACH STATEMENT EXECUTE FUNCTION railplan.deny_mutation();
CREATE TRIGGER score_history_immutable BEFORE UPDATE OR DELETE ON railplan.conflict_scores FOR EACH ROW EXECUTE FUNCTION railplan.deny_mutation();
CREATE TRIGGER score_history_no_truncate BEFORE TRUNCATE ON railplan.conflict_scores FOR EACH STATEMENT EXECUTE FUNCTION railplan.deny_mutation();
CREATE TRIGGER score_keys_immutable BEFORE UPDATE OR DELETE ON railplan.score_idempotency_keys FOR EACH ROW EXECUTE FUNCTION railplan.deny_mutation();
CREATE TRIGGER score_keys_no_truncate BEFORE TRUNCATE ON railplan.score_idempotency_keys FOR EACH STATEMENT EXECUTE FUNCTION railplan.deny_mutation();
CREATE TRIGGER score_audit AFTER INSERT ON railplan.conflict_scores FOR EACH ROW EXECUTE FUNCTION railplan.audit_change();
CREATE TRIGGER policy_activation_audit AFTER INSERT OR UPDATE OR DELETE ON railplan.scoring_policy_activations FOR EACH ROW EXECUTE FUNCTION railplan.audit_change();
REVOKE EXECUTE ON FUNCTION railplan.bump_scoring_revision(),railplan.bump_conflict_version() FROM PUBLIC;

ALTER TABLE railplan.scoring_policy_activations ADD CONSTRAINT activation_periods_do_not_overlap
 EXCLUDE USING gist(operator_id WITH =, tstzrange(starts_at,ends_at,'[)') WITH &&);
CREATE FUNCTION railplan.guard_scoring_activation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Activation history is retained'; END IF;
 IF TG_OP='UPDATE' AND (OLD.ends_at IS NOT NULL OR NEW.ends_at IS NULL OR
    (to_jsonb(NEW)-'ends_at') IS DISTINCT FROM (to_jsonb(OLD)-'ends_at')) THEN
   RAISE EXCEPTION 'An activation may only be closed once';
 END IF;
 IF NOT EXISTS(SELECT 1 FROM railplan.scoring_policies p WHERE p.id=NEW.policy_id
    AND p.operator_id=NEW.operator_id AND p.definition IS NOT NULL) THEN
   RAISE EXCEPTION 'Policy/operator mismatch';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER activation_guard BEFORE INSERT OR UPDATE OR DELETE ON railplan.scoring_policy_activations
 FOR EACH ROW EXECUTE FUNCTION railplan.guard_scoring_activation();
CREATE TRIGGER activation_no_truncate BEFORE TRUNCATE ON railplan.scoring_policy_activations
 FOR EACH STATEMENT EXECUTE FUNCTION railplan.deny_mutation();
REVOKE EXECUTE ON FUNCTION railplan.guard_scoring_activation() FROM PUBLIC;
