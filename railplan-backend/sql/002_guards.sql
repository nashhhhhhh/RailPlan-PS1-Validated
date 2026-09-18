SET search_path TO railplan, public;
CREATE FUNCTION deny_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION '% is append-only', TG_TABLE_NAME; END $$;

CREATE FUNCTION stamp_update() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at=clock_timestamp(); RETURN NEW; END $$;

CREATE FUNCTION audit_change() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE entity uuid; old_doc jsonb; new_doc jsonb;
BEGIN
 IF TG_OP <> 'INSERT' THEN old_doc=to_jsonb(OLD); END IF;
 IF TG_OP <> 'DELETE' THEN new_doc=to_jsonb(NEW); END IF;
 entity=COALESCE(NEW.id,OLD.id);
 INSERT INTO railplan.audit_logs(actor_id,action,entity_type,entity_id,before_state,after_state,correlation_id,source)
 VALUES(NULLIF(current_setting('railplan.actor_id',true),'')::uuid,TG_OP,TG_TABLE_NAME,entity,old_doc,new_doc,
 NULLIF(current_setting('railplan.correlation_id',true),'')::uuid,
 COALESCE(NULLIF(current_setting('railplan.source',true),''),'database'));
 RETURN COALESCE(NEW,OLD);
END $$;

CREATE FUNCTION request_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE w railplan.engineering_windows;
BEGIN
 SELECT * INTO STRICT w FROM railplan.engineering_windows WHERE id=NEW.window_id;
 IF NOT (w.period @> tstzrange(NEW.requested_start,NEW.requested_end,'[)')) THEN
 RAISE EXCEPTION 'Requested work must fit its engineering window';
 END IF;
 IF TG_OP='UPDATE' THEN
 NEW.version=OLD.version+1;
 IF OLD.submitted_at IS NOT NULL AND (NEW.requested_start,NEW.requested_end) IS DISTINCT FROM
 (OLD.requested_start,OLD.requested_end) THEN
 RAISE EXCEPTION 'Submitted requested timing is immutable; create a replacement request';
 END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER request_guard BEFORE INSERT OR UPDATE ON maintenance_requests FOR EACH ROW EXECUTE FUNCTION request_guard();

CREATE FUNCTION scenario_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='DELETE' THEN
   IF OLD.status <> 'draft' THEN RAISE EXCEPTION 'Submitted scenarios cannot be deleted'; END IF;
   RETURN OLD;
 END IF;
 IF OLD.status IN ('approved','superseded') THEN RAISE EXCEPTION 'Approved scenarios are immutable'; END IF;
 IF NEW.name IS DISTINCT FROM OLD.name OR NEW.run_id IS DISTINCT FROM OLD.run_id THEN
   IF OLD.status <> 'draft' THEN RAISE EXCEPTION 'Only draft scenarios may be edited'; END IF;
   NEW.validation_status='unvalidated';
 END IF;
 NEW.version=OLD.version+1;
 RETURN NEW;
END $$;
CREATE TRIGGER scenario_guard BEFORE UPDATE OR DELETE ON scenarios FOR EACH ROW EXECUTE FUNCTION scenario_guard();

CREATE FUNCTION scenario_child_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE doc jsonb; sid uuid; state text;
BEGIN
 doc=CASE WHEN TG_OP='DELETE' THEN to_jsonb(OLD) ELSE to_jsonb(NEW) END;
 IF TG_OP='UPDATE' AND
 (doc->>'scenario_id',doc->>'assignment_id',doc->>'possession_id') IS DISTINCT FROM
 (to_jsonb(OLD)->>'scenario_id',to_jsonb(OLD)->>'assignment_id',to_jsonb(OLD)->>'possession_id') THEN
 RAISE EXCEPTION 'Reparenting scenario content is forbidden';
 END IF;
 IF doc ? 'scenario_id' THEN sid=(doc->>'scenario_id')::uuid;
 ELSIF doc ? 'assignment_id' THEN
 SELECT scenario_id INTO sid FROM railplan.scenario_assignments WHERE id=(doc->>'assignment_id')::uuid;
 ELSE
 SELECT scenario_id INTO sid FROM railplan.possessions WHERE id=(doc->>'possession_id')::uuid;
 END IF;
 SELECT status INTO state FROM railplan.scenarios WHERE id=sid FOR UPDATE;
 IF state IS DISTINCT FROM 'draft' THEN RAISE EXCEPTION 'Scenario content is editable only in draft'; END IF;
 UPDATE railplan.scenarios SET validation_status='unvalidated' WHERE id=sid;
 RETURN COALESCE(NEW,OLD);
END $$;

CREATE FUNCTION assignment_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE r railplan.maintenance_requests; w uuid;
BEGIN
 SELECT * INTO STRICT r FROM railplan.maintenance_requests WHERE id=NEW.request_id;
 SELECT o.window_id INTO w FROM railplan.scenarios s JOIN railplan.optimisation_runs o ON o.id=s.run_id WHERE s.id=NEW.scenario_id;
 IF w<>r.window_id THEN RAISE EXCEPTION 'Cross-window assignment'; END IF;
 IF (NEW.original_start,NEW.original_end) IS DISTINCT FROM (r.requested_start,r.requested_end)
 OR NEW.request_version<>r.version THEN RAISE EXCEPTION 'Stale request snapshot'; END IF;
 IF NEW.starts_at<r.earliest_start OR NEW.ends_at>r.latest_finish OR
 extract(epoch FROM NEW.ends_at-NEW.starts_at)/60 NOT BETWEEN r.min_duration_minutes AND r.max_duration_minutes
 THEN RAISE EXCEPTION 'Assignment exceeds request limits'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER assignment_guard BEFORE INSERT OR UPDATE ON scenario_assignments FOR EACH ROW EXECUTE FUNCTION assignment_guard();

CREATE FUNCTION possession_link_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE p railplan.possessions; a railplan.scenario_assignments;
BEGIN
 SELECT * INTO STRICT p FROM railplan.possessions WHERE id=NEW.possession_id;
 SELECT * INTO STRICT a FROM railplan.scenario_assignments WHERE id=NEW.assignment_id;
 IF p.scenario_id<>a.scenario_id OR NOT(p.period @> a.period) THEN RAISE EXCEPTION 'Invalid possession membership'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER possession_link_guard BEFORE INSERT OR UPDATE ON possession_assignments FOR EACH ROW EXECUTE FUNCTION possession_link_guard();

CREATE FUNCTION window_period_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE w tstzrange;
BEGIN
 SELECT period INTO w FROM railplan.engineering_windows WHERE id=NEW.window_id;
 IF NOT(w @> tstzrange(NEW.starts_at,NEW.ends_at,'[)')) THEN RAISE EXCEPTION 'Period outside engineering window'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER window_period_guard BEFORE INSERT OR UPDATE ON window_periods FOR EACH ROW EXECUTE FUNCTION window_period_guard();
CREATE TRIGGER sector_period_guard BEFORE INSERT OR UPDATE ON sector_availability FOR EACH ROW EXECUTE FUNCTION window_period_guard();

-- Approval is persisted, but activating operational schedules is intentionally not exposed
-- until a domain validator and cross-window reservation service exist.
CREATE FUNCTION schedule_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE a railplan.approval_requests; s railplan.scenarios; w uuid;
BEGIN
 SELECT * INTO STRICT a FROM railplan.approval_requests WHERE id=NEW.approval_request_id;
 SELECT * INTO STRICT s FROM railplan.scenarios WHERE id=NEW.scenario_id;
 SELECT window_id INTO w FROM railplan.optimisation_runs WHERE id=s.run_id;
 IF a.status<>'approved' OR s.status<>'approved' OR s.validation_status<>'valid'
 OR a.scenario_id<>s.id OR w<>NEW.window_id THEN
 RAISE EXCEPTION 'Schedule requires a matching approved scenario and workflow';
 END IF;
 IF EXISTS(SELECT 1 FROM railplan.scenario_assignments sa
 JOIN railplan.maintenance_requests r ON r.id=sa.request_id
 WHERE sa.scenario_id=s.id AND (NOT sa.feasible OR sa.request_version<>r.version))
 THEN RAISE EXCEPTION 'Stale or infeasible assignments cannot be published'; END IF;
 IF NOT EXISTS(SELECT 1 FROM railplan.scenario_assignments WHERE scenario_id=s.id)
 THEN RAISE EXCEPTION 'Empty schedules cannot be published'; END IF;
 IF NOT EXISTS(SELECT 1 FROM railplan.approval_stages WHERE workflow_id=a.workflow_id)
 OR EXISTS(SELECT 1 FROM railplan.approval_stages st WHERE st.workflow_id=a.workflow_id AND NOT EXISTS(
 SELECT 1 FROM railplan.approval_decisions d WHERE d.approval_request_id=a.id AND d.stage_id=st.id AND d.decision='approved'))
 THEN RAISE EXCEPTION 'Incomplete approval stages'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER schedule_guard BEFORE INSERT ON schedule_versions FOR EACH ROW EXECUTE FUNCTION schedule_guard();

CREATE FUNCTION active_schedule_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM railplan.schedule_versions WHERE id=NEW.schedule_version_id AND window_id=NEW.window_id)
 THEN RAISE EXCEPTION 'Active schedule/window mismatch'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER active_schedule_guard BEFORE INSERT OR UPDATE ON active_schedules FOR EACH ROW EXECUTE FUNCTION active_schedule_guard();
CREATE TRIGGER freeze_content BEFORE INSERT OR UPDATE OR DELETE ON scenario_assignments FOR EACH ROW EXECUTE FUNCTION scenario_child_guard();
CREATE TRIGGER freeze_content BEFORE INSERT OR UPDATE OR DELETE ON scenario_sectors FOR EACH ROW EXECUTE FUNCTION scenario_child_guard();
CREATE TRIGGER freeze_content BEFORE INSERT OR UPDATE OR DELETE ON scenario_teams FOR EACH ROW EXECUTE FUNCTION scenario_child_guard();
CREATE TRIGGER freeze_content BEFORE INSERT OR UPDATE OR DELETE ON scenario_engineers FOR EACH ROW EXECUTE FUNCTION scenario_child_guard();
CREATE TRIGGER freeze_content BEFORE INSERT OR UPDATE OR DELETE ON scenario_equipment FOR EACH ROW EXECUTE FUNCTION scenario_child_guard();
CREATE TRIGGER freeze_content BEFORE INSERT OR UPDATE OR DELETE ON possessions FOR EACH ROW EXECUTE FUNCTION scenario_child_guard();
CREATE TRIGGER freeze_content BEFORE INSERT OR UPDATE OR DELETE ON possession_sectors FOR EACH ROW EXECUTE FUNCTION scenario_child_guard();
CREATE TRIGGER freeze_content BEFORE INSERT OR UPDATE OR DELETE ON possession_assignments FOR EACH ROW EXECUTE FUNCTION scenario_child_guard();
CREATE TRIGGER freeze_content BEFORE INSERT OR UPDATE OR DELETE ON isolation_plans FOR EACH ROW EXECUTE FUNCTION scenario_child_guard();
CREATE TRIGGER freeze_content BEFORE INSERT OR UPDATE OR DELETE ON scenario_metrics FOR EACH ROW EXECUTE FUNCTION scenario_child_guard();
CREATE TRIGGER touch_updated BEFORE UPDATE ON operators FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON operators FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON departments FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON departments FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON users FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON roles FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON roles FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON user_roles FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON user_roles FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON networks FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON networks FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON lines FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON lines FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON stations FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON stations FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON line_stations FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON line_stations FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON track_sectors FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON track_sectors FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON tracks FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON tracks FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON track_segments FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON track_segments FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON workzones FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON workzones FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON workzone_sectors FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON workzone_sectors FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON isolation_zones FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON isolation_zones FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON isolation_zone_sectors FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON isolation_zone_sectors FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON engineering_windows FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON engineering_windows FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON window_periods FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON window_periods FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON sector_availability FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON sector_availability FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON work_types FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON work_types FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON request_statuses FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON request_statuses FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON maintenance_requests FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON maintenance_requests FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON request_sectors FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON request_sectors FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON request_workzones FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON request_workzones FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON teams FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON teams FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON engineers FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON engineers FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON skills FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON skills FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON engineer_skills FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON engineer_skills FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON team_memberships FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON team_memberships FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON shifts FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON shifts FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON engineer_availability FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON engineer_availability FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON team_availability FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON team_availability FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON request_teams FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON request_teams FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON request_engineers FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON request_engineers FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON request_skills FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON request_skills FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON equipment_types FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON equipment_types FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON equipment_assets FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON equipment_assets FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON equipment_capabilities FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON equipment_capabilities FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON asset_capabilities FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON asset_capabilities FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON equipment_availability FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON equipment_availability FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON request_equipment_requirements FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON request_equipment_requirements FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON request_equipment_assets FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON request_equipment_assets FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON request_capabilities FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON request_capabilities FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON request_isolations FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON request_isolations FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON compatibility_rules FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON compatibility_rules FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON rule_definitions FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON rule_definitions FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON dependency_types FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON dependency_types FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON request_dependencies FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON request_dependencies FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON travel_times FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON travel_times FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON optimisation_objectives FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON optimisation_objectives FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON optimisation_runs FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON optimisation_runs FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON scenarios FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON scenarios FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON scenario_assignments FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON scenario_assignments FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON scenario_sectors FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON scenario_sectors FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON scenario_teams FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON scenario_teams FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON scenario_engineers FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON scenario_engineers FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON scenario_equipment FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON scenario_equipment FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON possessions FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON possessions FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON possession_sectors FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON possession_sectors FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON possession_assignments FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON possession_assignments FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON isolation_plans FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON isolation_plans FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON scenario_metrics FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON scenario_metrics FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON scoring_policies FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON scoring_policies FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON analysis_runs FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON analysis_runs FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON conflicts FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON conflicts FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON conflict_requests FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON conflict_requests FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON conflict_teams FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON conflict_teams FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON conflict_engineers FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON conflict_engineers FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON conflict_equipment FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON conflict_equipment FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON conflict_sectors FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON conflict_sectors FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON conflict_isolations FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON conflict_isolations FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON conflict_score_components FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON conflict_score_components FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON request_locks FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON request_locks FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON lock_fields FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON lock_fields FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON approval_workflows FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON approval_workflows FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON approval_stages FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON approval_stages FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON approval_requests FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON approval_requests FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER immutable_row BEFORE UPDATE OR DELETE ON approval_decisions FOR EACH ROW EXECUTE FUNCTION deny_mutation();
CREATE TRIGGER immutable_table BEFORE TRUNCATE ON approval_decisions FOR EACH STATEMENT EXECUTE FUNCTION deny_mutation();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON approval_decisions FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER immutable_row BEFORE UPDATE OR DELETE ON schedule_versions FOR EACH ROW EXECUTE FUNCTION deny_mutation();
CREATE TRIGGER immutable_table BEFORE TRUNCATE ON schedule_versions FOR EACH STATEMENT EXECUTE FUNCTION deny_mutation();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON schedule_versions FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON active_schedules FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON active_schedules FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER immutable_row BEFORE UPDATE OR DELETE ON audit_logs FOR EACH ROW EXECUTE FUNCTION deny_mutation();
CREATE TRIGGER immutable_table BEFORE TRUNCATE ON audit_logs FOR EACH STATEMENT EXECUTE FUNCTION deny_mutation();
CREATE TRIGGER immutable_row BEFORE UPDATE OR DELETE ON activity_events FOR EACH ROW EXECUTE FUNCTION deny_mutation();
CREATE TRIGGER immutable_table BEFORE TRUNCATE ON activity_events FOR EACH STATEMENT EXECUTE FUNCTION deny_mutation();
CREATE TRIGGER touch_updated BEFORE UPDATE ON event_reads FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER touch_updated BEFORE UPDATE ON copilot_conversations FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON copilot_conversations FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER immutable_row BEFORE UPDATE OR DELETE ON copilot_messages FOR EACH ROW EXECUTE FUNCTION deny_mutation();
CREATE TRIGGER immutable_table BEFORE TRUNCATE ON copilot_messages FOR EACH STATEMENT EXECUTE FUNCTION deny_mutation();
CREATE TRIGGER touch_updated BEFORE UPDATE ON copilot_tool_calls FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER touch_updated BEFORE UPDATE ON copilot_request_refs FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON copilot_request_refs FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON copilot_conflict_refs FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON copilot_conflict_refs FOR EACH ROW EXECUTE FUNCTION audit_change();
CREATE TRIGGER touch_updated BEFORE UPDATE ON copilot_scenario_refs FOR EACH ROW EXECUTE FUNCTION stamp_update();
CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON copilot_scenario_refs FOR EACH ROW EXECUTE FUNCTION audit_change();
REVOKE ALL ON SCHEMA railplan FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA railplan FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA railplan FROM PUBLIC;
REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA railplan FROM PUBLIC;
-- Approval-stage integrity is enforced even for direct database writes.
CREATE FUNCTION railplan.approval_decision_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE a railplan.approval_requests; st railplan.approval_stages; s railplan.scenarios;
BEGIN
 SELECT * INTO STRICT a FROM railplan.approval_requests WHERE id=NEW.approval_request_id FOR UPDATE;
 SELECT * INTO STRICT st FROM railplan.approval_stages WHERE id=NEW.stage_id;
 SELECT * INTO STRICT s FROM railplan.scenarios WHERE id=a.scenario_id FOR UPDATE;
 IF a.status<>'pending_review' OR s.status<>'pending_review' OR st.workflow_id<>a.workflow_id
 OR s.version<>a.scenario_version THEN RAISE EXCEPTION 'Stale or mismatched approval stage'; END IF;
 IF NEW.approver_id=a.submitted_by THEN RAISE EXCEPTION 'Self approval forbidden'; END IF;
 IF NOT EXISTS(SELECT 1 FROM railplan.users u JOIN railplan.user_roles ur ON ur.user_id=u.id
 WHERE u.id=NEW.approver_id AND u.active AND ur.role_id=st.required_role_id)
 THEN RAISE EXCEPTION 'Approver lacks the required active role'; END IF;
 IF EXISTS(SELECT 1 FROM railplan.approval_stages p WHERE p.workflow_id=a.workflow_id AND p.sequence_no<st.sequence_no
 AND NOT EXISTS(SELECT 1 FROM railplan.approval_decisions d WHERE d.approval_request_id=a.id AND d.stage_id=p.id AND d.decision='approved'))
 THEN RAISE EXCEPTION 'Earlier stages are incomplete'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER approval_decision_guard BEFORE INSERT ON railplan.approval_decisions
FOR EACH ROW EXECUTE FUNCTION railplan.approval_decision_guard();
REVOKE EXECUTE ON FUNCTION railplan.approval_decision_guard() FROM PUBLIC;
