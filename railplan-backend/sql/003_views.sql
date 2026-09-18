SET search_path TO railplan, public;
CREATE VIEW request_details AS
SELECT r.*, extract(epoch FROM r.requested_end-r.requested_start)/60 AS duration_minutes,
 (SELECT jsonb_agg(jsonb_build_object('id',s.id,'name',s.name,'code',s.code)) FROM request_sectors rs JOIN track_sectors s ON s.id=rs.sector_id WHERE rs.request_id=r.id) AS sectors,
 (SELECT jsonb_agg(jsonb_build_object('id',t.id,'name',t.name)) FROM request_teams rt JOIN teams t ON t.id=rt.team_id WHERE rt.request_id=r.id) AS teams,
 (SELECT jsonb_agg(jsonb_build_object('id',t.id,'name',t.name,'quantity',q.quantity)) FROM request_equipment_requirements q JOIN equipment_types t ON t.id=q.type_id WHERE q.request_id=r.id) AS equipment,
 EXISTS(SELECT 1 FROM request_locks l WHERE l.request_id=r.id AND l.scenario_id IS NULL AND l.released_at IS NULL AND (l.expires_at IS NULL OR l.expires_at>now())) AS is_locked
FROM maintenance_requests r;

CREATE VIEW engineering_timeline AS
SELECT r.id AS request_id,r.request_code,r.title,r.window_id,NULL::uuid AS scenario_id,
 r.requested_start AS starts_at,r.requested_end AS ends_at,r.requested_start AS original_start,r.requested_end AS original_end,
 0::numeric AS movement_minutes,false AS moved,r.priority FROM maintenance_requests r
UNION ALL
SELECT r.id,r.request_code,r.title,r.window_id,a.scenario_id,a.starts_at,a.ends_at,a.original_start,a.original_end,
 extract(epoch FROM a.starts_at-a.original_start)/60,
 (a.starts_at,a.ends_at) IS DISTINCT FROM (a.original_start,a.original_end),r.priority
FROM scenario_assignments a JOIN maintenance_requests r ON r.id=a.request_id;

CREATE VIEW coordination_queue AS
SELECT c.*,a.window_id,a.scenario_id,rd.code AS rule_code,rd.category AS lens,rd.blocking,
 (SELECT jsonb_agg(jsonb_build_object('id',r.id,'code',r.request_code)) FROM conflict_requests cr
 JOIN maintenance_requests r ON r.id=cr.request_id WHERE cr.conflict_id=c.id) AS requests
FROM conflicts c JOIN analysis_runs a ON a.id=c.analysis_run_id JOIN rule_definitions rd ON rd.id=c.rule_id;

CREATE VIEW scenario_comparison AS
SELECT s.id,s.name,s.status,s.validation_status,s.provenance,o.window_id,ob.name AS objective,
 o.status AS solver_status,m.conflicts_resolved,m.unresolved_conflicts,m.possession_count,
 m.disruption_score,m.resource_utilisation,m.unscheduled_requests,
 (SELECT count(*) FROM scenario_assignments a WHERE a.scenario_id=s.id AND
 (a.starts_at,a.ends_at) IS DISTINCT FROM (a.original_start,a.original_end)) AS requests_moved,
 (SELECT sum(abs(extract(epoch FROM a.starts_at-a.original_start)/60)) FROM scenario_assignments a WHERE a.scenario_id=s.id) AS total_movement_minutes
FROM scenarios s JOIN optimisation_runs o ON o.id=s.run_id JOIN optimisation_objectives ob ON ob.id=o.objective_id
LEFT JOIN scenario_metrics m ON m.scenario_id=s.id;

CREATE VIEW change_replay AS
SELECT a.scenario_id,r.request_code,a.request_id,a.original_start,a.original_end,a.starts_at,a.ends_at,a.reason,
 row_number() OVER(PARTITION BY a.scenario_id ORDER BY a.starts_at,r.request_code) AS replay_order
FROM scenario_assignments a JOIN maintenance_requests r ON r.id=a.request_id
WHERE (a.starts_at,a.ends_at) IS DISTINCT FROM(a.original_start,a.original_end);

CREATE VIEW approval_summary AS
SELECT ar.*,s.name AS scenario_name,
 (SELECT count(*) FROM approval_stages st WHERE st.workflow_id=ar.workflow_id) AS required_stages,
 (SELECT count(*) FROM approval_decisions d WHERE d.approval_request_id=ar.id AND d.decision='approved') AS approved_stages
FROM approval_requests ar JOIN scenarios s ON s.id=ar.scenario_id;

CREATE VIEW resource_availability AS
SELECT 'engineer'::text AS resource_type,engineer_id AS resource_id,available,starts_at,ends_at,reason FROM engineer_availability
UNION ALL SELECT 'team',team_id,available,starts_at,ends_at,reason FROM team_availability
UNION ALL SELECT 'equipment',asset_id,available,starts_at,ends_at,reason FROM equipment_availability;

CREATE VIEW operational_activity AS
SELECT e.*,u.display_name AS actor_name FROM activity_events e LEFT JOIN users u ON u.id=e.actor_id;
