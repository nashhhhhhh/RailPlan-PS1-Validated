"""One statement-level MVCC snapshot: bounded schedule, policies and evidence.

SQL identifiers are developer constants. All scope values are bound parameters.
Spatial measurements use PostGIS geography (metres), never UI coordinates.
"""
from sqlalchemy import text


PREFIX = """
WITH req AS MATERIALIZED (
 SELECT * FROM railplan.maintenance_requests
 WHERE window_id=:window_id AND status_code NOT IN ('cancelled','rejected')
), jobs AS MATERIALIZED (
 SELECT r.*,r.requested_start AS starts_at,r.requested_end AS ends_at,
 r.requested_period AS period,NULL::uuid AS assignment_id,r.version AS assignment_version
 FROM req r WHERE CAST(:scenario_id AS uuid) IS NULL
 UNION ALL
 SELECT r.*,a.starts_at,a.ends_at,a.period,a.id,a.request_version
 FROM req r JOIN railplan.scenario_assignments a ON a.request_id=r.id
 WHERE a.scenario_id=CAST(:scenario_id AS uuid)
), sectors AS (
 SELECT j.id AS request_id,s.sector_id FROM jobs j
 JOIN railplan.request_sectors s ON s.request_id=j.id WHERE j.assignment_id IS NULL
 UNION
 SELECT j.id,s.sector_id FROM jobs j JOIN railplan.scenario_sectors s ON s.assignment_id=j.assignment_id
), teams AS (
 SELECT j.id AS request_id,t.team_id FROM jobs j
 JOIN railplan.request_teams t ON t.request_id=j.id WHERE j.assignment_id IS NULL
 UNION
 SELECT j.id,t.team_id FROM jobs j JOIN railplan.scenario_teams t ON t.assignment_id=j.assignment_id
), engineers AS (
 SELECT j.id AS request_id,e.engineer_id,j.starts_at,j.ends_at FROM jobs j
 JOIN railplan.request_engineers e ON e.request_id=j.id WHERE j.assignment_id IS NULL
 UNION
 SELECT j.id,e.engineer_id,j.starts_at,j.ends_at FROM jobs j
 JOIN railplan.scenario_engineers e ON e.assignment_id=j.assignment_id
 UNION
 SELECT j.id,m.engineer_id,greatest(j.starts_at,m.starts_at),least(j.ends_at,m.ends_at)
 FROM jobs j JOIN teams t ON t.request_id=j.id
 JOIN railplan.team_memberships m ON m.team_id=t.team_id AND m.period && j.period
), assets AS (
 SELECT j.id AS request_id,e.asset_id FROM jobs j
 JOIN railplan.request_equipment_assets e ON e.request_id=j.id WHERE j.assignment_id IS NULL
 UNION
 SELECT j.id,e.asset_id FROM jobs j JOIN railplan.scenario_equipment e ON e.assignment_id=j.assignment_id
), pairs AS MATERIALIZED (
 SELECT a.id AS first_id,b.id AS second_id FROM jobs a JOIN jobs b ON a.id<b.id AND a.period && b.period
), compatibility AS MATERIALIZED (
 SELECT DISTINCT ON (first_work_type_id,second_work_type_id) c.*
 FROM railplan.compatibility_rules c
 WHERE first_work_type_id IN (SELECT work_type_id FROM jobs)
 AND second_work_type_id IN (SELECT work_type_id FROM jobs)
 ORDER BY first_work_type_id,second_work_type_id,version DESC
), zones AS MATERIALIZED (
 SELECT rw.request_id,w.id,w.name,w.geometry_source,w.geom,
 (w.geom IS NOT NULL AND NOT ST_IsEmpty(w.geom) AND ST_IsValid(w.geom)
 AND w.geometry_source='verified') AS usable
 FROM railplan.request_workzones rw JOIN jobs j ON j.id=rw.request_id
 JOIN railplan.workzones w ON w.id=rw.workzone_id
), spatial AS (
 SELECT p.first_id,p.second_id,a.id AS first_zone_id,b.id AS second_zone_id,
 CASE WHEN a.usable AND b.usable THEN ST_Intersects(a.geom,b.geom) END AS intersects,
 CASE WHEN a.usable AND b.usable THEN ST_Distance(a.geom::geography,b.geom::geography) END AS distance_metres,
 CASE WHEN a.usable AND b.usable AND c.id IS NOT NULL THEN
 ST_DWithin(a.geom::geography,b.geom::geography,c.minimum_separation_metres) END AS within_limit
 FROM pairs p JOIN jobs ja ON ja.id=p.first_id JOIN jobs jb ON jb.id=p.second_id
 JOIN zones a ON a.request_id=p.first_id JOIN zones b ON b.request_id=p.second_id
 LEFT JOIN compatibility c ON c.first_work_type_id=least(ja.work_type_id,jb.work_type_id)
 AND c.second_work_type_id=greatest(ja.work_type_id,jb.work_type_id)
)
"""

# Each expression returns rows only for this analysis's requests/resources.
SOURCES = {
    "jobs": "SELECT to_jsonb(j)-'period'-'requested_period' AS doc FROM jobs j",
    "sectors": "SELECT to_jsonb(s) AS doc FROM sectors s",
    "teams": "SELECT to_jsonb(t) AS doc FROM teams t",
    "engineers": "SELECT to_jsonb(e) AS doc FROM engineers e",
    "assets": "SELECT to_jsonb(a) AS doc FROM assets a",
    "pairs": "SELECT to_jsonb(p) AS doc FROM pairs p",
    "compatibility": "SELECT to_jsonb(c) AS doc FROM compatibility c",
    "zones": "SELECT to_jsonb(z)-'geom' || jsonb_build_object('geometry',ST_AsGeoJSON(z.geom)::jsonb) AS doc FROM zones z",
    "spatial": "SELECT to_jsonb(s) AS doc FROM spatial s",
    "rules": "SELECT to_jsonb(r) AS doc FROM (SELECT DISTINCT ON (code) * FROM railplan.rule_definitions ORDER BY code,version DESC) r",
    "engineer_records": "SELECT to_jsonb(e) AS doc FROM railplan.engineers e WHERE e.id IN (SELECT engineer_id FROM engineers)",
    "asset_records": "SELECT to_jsonb(e) AS doc FROM railplan.equipment_assets e WHERE e.id IN (SELECT asset_id FROM assets)",
    "team_records": "SELECT to_jsonb(t) AS doc FROM railplan.teams t WHERE t.id IN (SELECT team_id FROM teams)",
    "memberships": "SELECT to_jsonb(m)-'period' AS doc FROM railplan.team_memberships m WHERE team_id IN (SELECT team_id FROM teams)",
    "isolation_records": "SELECT to_jsonb(z)-'geom' AS doc FROM railplan.isolation_zones z WHERE id IN (SELECT isolation_zone_id FROM railplan.request_isolations WHERE request_id IN (SELECT id FROM jobs))",
    "engineer_availability": "SELECT to_jsonb(a)-'period' AS doc FROM railplan.engineer_availability a WHERE engineer_id IN (SELECT engineer_id FROM engineers)",
    "team_availability": "SELECT to_jsonb(a)-'period' AS doc FROM railplan.team_availability a WHERE team_id IN (SELECT team_id FROM teams)",
    "equipment_availability": "SELECT to_jsonb(a)-'period' AS doc FROM railplan.equipment_availability a WHERE asset_id IN (SELECT asset_id FROM assets)",
    "sector_availability": "SELECT to_jsonb(a)-'period' AS doc FROM railplan.sector_availability a WHERE window_id=:window_id AND sector_id IN (SELECT sector_id FROM sectors)",
    "skills": "SELECT to_jsonb(s)-'period' AS doc FROM railplan.engineer_skills s WHERE engineer_id IN (SELECT engineer_id FROM engineers)",
    "asset_capabilities": "SELECT to_jsonb(c) AS doc FROM railplan.asset_capabilities c WHERE asset_id IN (SELECT asset_id FROM assets)",
    "dependencies": "SELECT to_jsonb(d) || jsonb_build_object('code',t.code) AS doc FROM railplan.request_dependencies d JOIN railplan.dependency_types t ON t.id=d.dependency_type_id WHERE predecessor_id IN (SELECT id FROM req) OR successor_id IN (SELECT id FROM req)",
    "travel": "SELECT to_jsonb(t) AS doc FROM railplan.travel_times t WHERE from_sector_id IN (SELECT sector_id FROM sectors) AND to_sector_id IN (SELECT sector_id FROM sectors)",
    "unassigned": "SELECT jsonb_build_object('id',r.id,'request_code',r.request_code) AS doc FROM req r WHERE r.id NOT IN (SELECT id FROM jobs)",
}
for key, table in (
    ("required_skills", "request_skills"),
    ("required_equipment", "request_equipment_requirements"),
    ("required_capabilities", "request_capabilities"),
    ("isolations", "request_isolations"),
):
    SOURCES[key] = f"SELECT to_jsonb(t) AS doc FROM railplan.{table} t WHERE request_id IN (SELECT id FROM jobs)"

SNAPSHOT_SQL = PREFIX + "SELECT jsonb_build_object(" + ",".join(
    f"'{key}',(SELECT coalesce(jsonb_agg(doc ORDER BY doc::text),'[]'::jsonb) FROM ({sql}) data)"
    for key, sql in SOURCES.items()
) + """,'window',(SELECT to_jsonb(w)-'period' FROM railplan.engineering_windows w WHERE id=:window_id),
'scenario',(SELECT to_jsonb(s) FROM railplan.scenarios s WHERE id=CAST(:scenario_id AS uuid)),
'scope','single_window','complete_solver_input',false,'engine_version','1.0')"""


def capture_snapshot(db, window_id, scenario_id):
    return db.execute(text(SNAPSHOT_SQL), {"window_id": window_id, "scenario_id": scenario_id}).scalar_one()
