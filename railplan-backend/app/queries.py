"""Parameterized query catalogue. Overlap results are candidates, not safety certification."""
QUERIES = {
"temporal_overlaps": """
SELECT a.id AS first_request_id,b.id AS second_request_id,
       a.requested_period * b.requested_period AS overlap
FROM railplan.maintenance_requests a JOIN railplan.maintenance_requests b
 ON a.id<b.id AND a.requested_period && b.requested_period
WHERE a.window_id=:window_id AND b.window_id=:window_id
 AND a.status_code NOT IN ('cancelled','rejected') AND b.status_code NOT IN ('cancelled','rejected')
""",
"sector_overlaps": """
SELECT DISTINCT a.request_id AS first_request_id,b.request_id AS second_request_id,a.sector_id
FROM railplan.request_sectors a JOIN railplan.request_sectors b ON a.sector_id=b.sector_id AND a.request_id<b.request_id
JOIN railplan.maintenance_requests ra ON ra.id=a.request_id
JOIN railplan.maintenance_requests rb ON rb.id=b.request_id
WHERE ra.window_id=:window_id AND rb.window_id=:window_id AND ra.requested_period && rb.requested_period
""",
"workzone_intersections": """
SELECT DISTINCT a.request_id AS first_request_id,b.request_id AS second_request_id
FROM railplan.request_workzones a JOIN railplan.request_workzones b ON a.request_id<b.request_id
JOIN railplan.workzones wa ON wa.id=a.workzone_id JOIN railplan.workzones wb ON wb.id=b.workzone_id
JOIN railplan.maintenance_requests ra ON ra.id=a.request_id JOIN railplan.maintenance_requests rb ON rb.id=b.request_id
WHERE ra.window_id=:window_id AND rb.window_id=:window_id AND ra.requested_period && rb.requested_period
 AND ST_Intersects(wa.geom,wb.geom)
""",
"nearby_workzones": """
SELECT a.id,b.id FROM railplan.workzones a JOIN railplan.workzones b ON a.id<b.id
WHERE a.network_id=:network_id AND b.network_id=:network_id
AND ST_DWithin(a.geom::geography,b.geom::geography,:metres)
""",
"team_double_booking": """
SELECT a.request_id AS first_request_id,b.request_id AS second_request_id,a.team_id
FROM railplan.request_teams a JOIN railplan.request_teams b ON a.team_id=b.team_id AND a.request_id<b.request_id
JOIN railplan.maintenance_requests ra ON ra.id=a.request_id JOIN railplan.maintenance_requests rb ON rb.id=b.request_id
WHERE ra.window_id=:window_id AND rb.window_id=:window_id AND ra.requested_period && rb.requested_period
""",
"engineer_double_booking": """
WITH assigned AS (
 SELECT re.request_id,re.engineer_id,r.requested_period AS period,r.window_id
 FROM railplan.request_engineers re JOIN railplan.maintenance_requests r ON r.id=re.request_id
 UNION
 SELECT rt.request_id,tm.engineer_id,r.requested_period * tm.period AS period,r.window_id
 FROM railplan.request_teams rt JOIN railplan.team_memberships tm ON tm.team_id=rt.team_id
 JOIN railplan.maintenance_requests r ON r.id=rt.request_id WHERE r.requested_period && tm.period
)
SELECT DISTINCT a.request_id AS first_request_id,b.request_id AS second_request_id,a.engineer_id
FROM assigned a JOIN assigned b ON a.engineer_id=b.engineer_id AND a.request_id<b.request_id AND a.period && b.period
WHERE a.window_id=:window_id AND b.window_id=:window_id
""",
"equipment_double_booking": """
SELECT a.request_id AS first_request_id,b.request_id AS second_request_id,a.asset_id
FROM railplan.request_equipment_assets a JOIN railplan.request_equipment_assets b
 ON a.asset_id=b.asset_id AND a.request_id<b.request_id
JOIN railplan.maintenance_requests ra ON ra.id=a.request_id JOIN railplan.maintenance_requests rb ON rb.id=b.request_id
WHERE ra.window_id=:window_id AND rb.window_id=:window_id AND ra.requested_period && rb.requested_period
""",
"isolation_conflicts": """
SELECT a.request_id AS first_request_id,b.request_id AS second_request_id,a.isolation_zone_id
FROM railplan.request_isolations a JOIN railplan.request_isolations b
 ON a.isolation_zone_id=b.isolation_zone_id AND a.request_id<b.request_id AND a.required_state<>b.required_state
JOIN railplan.maintenance_requests ra ON ra.id=a.request_id JOIN railplan.maintenance_requests rb ON rb.id=b.request_id
WHERE ra.window_id=:window_id AND rb.window_id=:window_id AND ra.requested_period && rb.requested_period
""",
"dependency_violations": """
SELECT d.*,dt.code FROM railplan.request_dependencies d
JOIN railplan.dependency_types dt ON dt.id=d.dependency_type_id
JOIN railplan.maintenance_requests a ON a.id=d.predecessor_id
JOIN railplan.maintenance_requests b ON b.id=d.successor_id
WHERE a.window_id=:window_id AND
CASE dt.code
 WHEN 'finish_to_start' THEN b.requested_start<a.requested_end+make_interval(mins=>d.lag_minutes)
 WHEN 'start_to_start' THEN b.requested_start<a.requested_start+make_interval(mins=>d.lag_minutes)
 WHEN 'finish_to_finish' THEN b.requested_end<a.requested_end+make_interval(mins=>d.lag_minutes)
 ELSE false END
""",
"request_conflicts": """
SELECT q.* FROM railplan.coordination_queue q
JOIN railplan.conflict_requests cr ON cr.conflict_id=q.id
WHERE cr.request_id=:request_id AND q.analysis_run_id=:analysis_run_id
""",
"compare_timings": """
SELECT * FROM railplan.change_replay WHERE scenario_id=:scenario_id ORDER BY replay_order
""",
"available_qualified_engineers": """
WITH target AS (SELECT * FROM railplan.maintenance_requests WHERE id=:request_id)
SELECT e.id,e.name FROM railplan.engineers e CROSS JOIN target r
WHERE e.active AND e.department_id=r.department_id
AND EXISTS(SELECT 1 FROM railplan.engineer_availability av WHERE av.engineer_id=e.id AND av.available AND av.period @> r.requested_period)
AND NOT EXISTS(SELECT 1 FROM railplan.engineer_availability av WHERE av.engineer_id=e.id AND NOT av.available AND av.period && r.requested_period)
AND NOT EXISTS(
 SELECT 1 FROM railplan.request_skills rs WHERE rs.request_id=r.id AND NOT EXISTS(
 SELECT 1 FROM railplan.engineer_skills es WHERE es.engineer_id=e.id AND es.skill_id=rs.skill_id AND es.period @> r.requested_period))
AND NOT EXISTS(
 SELECT 1 FROM railplan.scenario_engineers se JOIN railplan.scenario_assignments sa ON sa.id=se.assignment_id
 WHERE se.engineer_id=e.id AND sa.scenario_id=:scenario_id AND sa.request_id<>r.id AND sa.period && r.requested_period)
-- Candidate filtering only: team-derived assignments, travel and aggregate headcount must be checked by the future validator.
""",
"travel_violations": """
SELECT aa.request_id AS first_request_id,bb.request_id AS second_request_id,a.engineer_id,t.minutes
FROM railplan.scenario_engineers a JOIN railplan.scenario_engineers b ON a.engineer_id=b.engineer_id AND a.assignment_id<>b.assignment_id
JOIN railplan.scenario_assignments aa ON aa.id=a.assignment_id
JOIN railplan.scenario_assignments bb ON bb.id=b.assignment_id
JOIN railplan.scenario_sectors sa ON sa.assignment_id=aa.id
JOIN railplan.scenario_sectors sb ON sb.assignment_id=bb.id
JOIN railplan.travel_times t ON t.from_sector_id=sa.sector_id AND t.to_sector_id=sb.sector_id
WHERE aa.scenario_id=:scenario_id AND bb.scenario_id=:scenario_id AND aa.ends_at<=bb.starts_at
AND bb.starts_at<aa.ends_at+make_interval(mins=>t.minutes)
""",
"command_centre": """
SELECT jsonb_build_object(
 'requests',(SELECT jsonb_agg(to_jsonb(r)-'requested_period') FROM railplan.request_details r WHERE r.window_id=:window_id),
 'timeline',(SELECT jsonb_agg(to_jsonb(t)) FROM railplan.engineering_timeline t WHERE t.window_id=:window_id AND t.scenario_id IS NOT DISTINCT FROM CAST(:scenario_id AS uuid)),
 'conflicts',(SELECT jsonb_agg(to_jsonb(c)) FROM railplan.coordination_queue c WHERE c.window_id=:window_id AND c.analysis_run_id=(
 SELECT id FROM railplan.analysis_runs WHERE window_id=:window_id AND scenario_id IS NOT DISTINCT FROM CAST(:scenario_id AS uuid) AND status='completed' ORDER BY created_at DESC,id DESC LIMIT 1)),
 'scenarios',(SELECT jsonb_agg(to_jsonb(s)) FROM railplan.scenario_comparison s WHERE s.window_id=:window_id)
) AS payload
"""
}
