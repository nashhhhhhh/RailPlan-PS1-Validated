-- Additive migration: preserve terminal analyses and their machine findings.
SET search_path TO railplan, public;

CREATE FUNCTION analysis_history_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF OLD.status IN ('completed','failed') THEN
   RAISE EXCEPTION 'Terminal analysis results are immutable; create a new analysis';
 END IF;
 RETURN COALESCE(NEW,OLD);
END $$;
CREATE TRIGGER analysis_history_guard BEFORE UPDATE OR DELETE ON analysis_runs
 FOR EACH ROW EXECUTE FUNCTION analysis_history_guard();
CREATE TRIGGER immutable_table BEFORE TRUNCATE ON analysis_runs
 FOR EACH STATEMENT EXECUTE FUNCTION deny_mutation();

CREATE FUNCTION conflict_history_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE doc jsonb; aid uuid; cid uuid; state text; synthetic boolean;
BEGIN
 doc=CASE WHEN TG_OP='DELETE' THEN to_jsonb(OLD) ELSE to_jsonb(NEW) END;
 IF TG_OP='UPDATE' AND
 (doc->>'analysis_run_id',doc->>'conflict_id') IS DISTINCT FROM
 (to_jsonb(OLD)->>'analysis_run_id',to_jsonb(OLD)->>'conflict_id') THEN
   RAISE EXCEPTION 'Reparenting analysis evidence is forbidden';
 END IF;
 IF TG_TABLE_NAME='conflicts' THEN aid=(doc->>'analysis_run_id')::uuid;
 ELSE
   cid=(doc->>'conflict_id')::uuid;
   SELECT analysis_run_id INTO aid FROM railplan.conflicts WHERE id=cid;
 END IF;
 SELECT status,coalesce((input_snapshot->>'synthetic')::boolean,false) INTO state,synthetic
 FROM railplan.analysis_runs WHERE id=aid FOR UPDATE;
 -- Legacy synthetic records may be inserted for the offline UI demonstration.
 IF TG_OP='INSERT' AND synthetic THEN
   IF TG_TABLE_NAME='conflicts' AND doc->>'detection_method'='synthetic' THEN RETURN NEW; END IF;
   IF TG_TABLE_NAME<>'conflicts' AND EXISTS(
     SELECT 1 FROM railplan.conflicts WHERE id=cid AND detection_method='synthetic'
   ) THEN RETURN NEW; END IF;
 END IF;
 IF state IN ('completed','failed') THEN
   RAISE EXCEPTION 'Terminal analysis evidence is immutable';
 END IF;
 RETURN COALESCE(NEW,OLD);
END $$;

DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['conflicts','conflict_requests','conflict_teams','conflict_engineers',
   'conflict_equipment','conflict_sectors','conflict_isolations','conflict_score_components'] LOOP
   EXECUTE format('CREATE TRIGGER conflict_history_guard BEFORE INSERT OR UPDATE OR DELETE ON %I FOR EACH ROW EXECUTE FUNCTION conflict_history_guard()',t);
   EXECUTE format('CREATE TRIGGER immutable_table BEFORE TRUNCATE ON %I FOR EACH STATEMENT EXECUTE FUNCTION deny_mutation()',t);
 END LOOP;
END $$;

-- Keep the exact existing projection columns and order; use captured policy for
-- automatic runs, with legacy lookup fallback for synthetic demo records.
CREATE OR REPLACE VIEW coordination_queue AS
SELECT c.id,c.conflict_code,c.analysis_run_id,c.rule_id,c.title,c.explanation,
 c.severity,c.risk_score,c.resolution_status,c.resolution_notes,c.detection_method,
 c.detected_at,c.created_at,c.updated_at,a.window_id,a.scenario_id,coalesce(s.rule->>'code',rd.code) AS rule_code,
 coalesce(s.rule->>'category',rd.category) AS lens,
 coalesce((s.rule->>'blocking')::boolean,rd.blocking) AS blocking,
 (SELECT jsonb_agg(jsonb_build_object('id',r.id,'code',r.request_code)) FROM conflict_requests cr
 JOIN maintenance_requests r ON r.id=cr.request_id WHERE cr.conflict_id=c.id) AS requests
FROM conflicts c JOIN analysis_runs a ON a.id=c.analysis_run_id
JOIN rule_definitions rd ON rd.id=c.rule_id
LEFT JOIN LATERAL (SELECT value AS rule FROM jsonb_array_elements(
 CASE WHEN jsonb_typeof(a.rule_snapshot)='array' THEN a.rule_snapshot ELSE '[]'::jsonb END)
 WHERE value->>'id'=c.rule_id::text LIMIT 1) s ON true;
