-- RailPlan PostgreSQL 16 / PostGIS. Migration-owner execution only.
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS btree_gist;
CREATE SCHEMA railplan;
SET search_path TO railplan, public;
CREATE SEQUENCE request_code_seq START 1000;
CREATE SEQUENCE conflict_code_seq START 1000;

CREATE TABLE operators (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code text NOT NULL UNIQUE,
  name text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE departments (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  operator_id uuid NOT NULL REFERENCES operators(id) ON DELETE RESTRICT,
  name text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(operator_id,name)
);

CREATE TABLE users (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  department_id uuid NOT NULL REFERENCES departments(id) ON DELETE RESTRICT,
  auth_subject text NOT NULL UNIQUE,
  display_name text NOT NULL,
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE roles (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code text NOT NULL UNIQUE,
  name text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE user_roles (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  role_id uuid NOT NULL REFERENCES roles(id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(user_id,role_id)
);

CREATE TABLE networks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  operator_id uuid NOT NULL REFERENCES operators(id) ON DELETE RESTRICT,
  code text NOT NULL UNIQUE,
  name text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE lines (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  network_id uuid NOT NULL REFERENCES networks(id) ON DELETE RESTRICT,
  code text NOT NULL UNIQUE,
  name text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE stations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  network_id uuid NOT NULL REFERENCES networks(id) ON DELETE RESTRICT,
  name text NOT NULL,
  geom geometry(Point,4326),
  geometry_source text NOT NULL DEFAULT 'unverified',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE line_stations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  line_id uuid NOT NULL REFERENCES lines(id) ON DELETE RESTRICT,
  station_id uuid NOT NULL REFERENCES stations(id) ON DELETE RESTRICT,
  code text NOT NULL UNIQUE,
  sequence_no integer NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(line_id,station_id),
  UNIQUE(line_id,sequence_no)
);

CREATE TABLE track_sectors (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  line_id uuid NOT NULL REFERENCES lines(id) ON DELETE RESTRICT,
  from_station_id uuid NOT NULL REFERENCES stations(id) ON DELETE RESTRICT,
  to_station_id uuid NOT NULL REFERENCES stations(id) ON DELETE RESTRICT,
  code text NOT NULL UNIQUE,
  name text NOT NULL,
  geom geometry(MultiLineString,4326),
  geometry_source text NOT NULL DEFAULT 'unverified',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK(from_station_id <> to_station_id)
);

CREATE TABLE tracks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  sector_id uuid NOT NULL REFERENCES track_sectors(id) ON DELETE RESTRICT,
  code text NOT NULL,
  direction text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(sector_id,code)
);

CREATE TABLE track_segments (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  track_id uuid NOT NULL REFERENCES tracks(id) ON DELETE RESTRICT,
  code text NOT NULL UNIQUE,
  geom geometry(LineString,4326),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE workzones (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  network_id uuid NOT NULL REFERENCES networks(id) ON DELETE RESTRICT,
  code text NOT NULL UNIQUE,
  name text NOT NULL,
  geom geometry(MultiPolygon,4326),
  geometry_source text NOT NULL DEFAULT 'unverified',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK(geom IS NULL OR ST_IsValid(geom))
);

CREATE TABLE workzone_sectors (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  workzone_id uuid NOT NULL REFERENCES workzones(id) ON DELETE RESTRICT,
  sector_id uuid NOT NULL REFERENCES track_sectors(id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(workzone_id,sector_id)
);

CREATE TABLE isolation_zones (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  network_id uuid NOT NULL REFERENCES networks(id) ON DELETE RESTRICT,
  code text NOT NULL UNIQUE,
  name text NOT NULL,
  geom geometry(MultiPolygon,4326),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE isolation_zone_sectors (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  isolation_zone_id uuid NOT NULL REFERENCES isolation_zones(id) ON DELETE RESTRICT,
  sector_id uuid NOT NULL REFERENCES track_sectors(id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(isolation_zone_id,sector_id)
);

CREATE TABLE engineering_windows (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  line_id uuid NOT NULL REFERENCES lines(id) ON DELETE RESTRICT,
  name text NOT NULL,
  service_date date NOT NULL,
  timezone text NOT NULL DEFAULT 'Asia/Singapore',
  starts_at timestamptz NOT NULL,
  ends_at timestamptz NOT NULL,
  period tstzrange GENERATED ALWAYS AS (tstzrange(starts_at, ends_at, '[)')) STORED,
  version integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (isfinite(starts_at) AND isfinite(ends_at) AND ends_at > starts_at),
  CHECK(version > 0)
);

CREATE TABLE window_periods (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  window_id uuid NOT NULL REFERENCES engineering_windows(id) ON DELETE RESTRICT,
  kind text NOT NULL,
  starts_at timestamptz NOT NULL,
  ends_at timestamptz NOT NULL,
  period tstzrange GENERATED ALWAYS AS (tstzrange(starts_at, ends_at, '[)')) STORED,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK(kind IN ('permitted_work','service_shutdown')),
  CHECK (isfinite(starts_at) AND isfinite(ends_at) AND ends_at > starts_at)
);

CREATE TABLE sector_availability (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  window_id uuid NOT NULL REFERENCES engineering_windows(id) ON DELETE RESTRICT,
  sector_id uuid NOT NULL REFERENCES track_sectors(id) ON DELETE RESTRICT,
  available boolean NOT NULL,
  starts_at timestamptz NOT NULL,
  ends_at timestamptz NOT NULL,
  period tstzrange GENERATED ALWAYS AS (tstzrange(starts_at, ends_at, '[)')) STORED,
  reason text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (isfinite(starts_at) AND isfinite(ends_at) AND ends_at > starts_at)
);

CREATE TABLE work_types (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code text NOT NULL UNIQUE,
  name text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE request_statuses (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code text NOT NULL UNIQUE,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE maintenance_requests (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  request_code text NOT NULL UNIQUE DEFAULT ('MR-' || lpad(nextval('request_code_seq')::text,6,'0')),
  window_id uuid NOT NULL REFERENCES engineering_windows(id) ON DELETE RESTRICT,
  department_id uuid NOT NULL REFERENCES departments(id) ON DELETE RESTRICT,
  work_type_id uuid NOT NULL REFERENCES work_types(id) ON DELETE RESTRICT,
  title text NOT NULL CHECK(length(trim(title)) > 0),
  description text NOT NULL DEFAULT '',
  priority text NOT NULL DEFAULT 'normal',
  status_code text NOT NULL REFERENCES request_statuses(code) DEFAULT 'draft',
  requested_start timestamptz NOT NULL,
  requested_end timestamptz NOT NULL,
  requested_period tstzrange GENERATED ALWAYS AS (tstzrange(requested_start,requested_end,'[)')) STORED,
  min_duration_minutes integer NOT NULL,
  max_duration_minutes integer NOT NULL,
  earliest_start timestamptz NOT NULL,
  latest_finish timestamptz NOT NULL,
  flexibility text NOT NULL DEFAULT 'flexible',
  operational_impact text,
  safety_classification text NOT NULL DEFAULT 'unreviewed',
  created_by uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  submitted_by uuid REFERENCES users(id) ON DELETE RESTRICT,
  submitted_at timestamptz,
  cancelled_at timestamptz,
  cancellation_reason text,
  version integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK(priority IN ('normal','high','urgent')),
  CHECK(flexibility IN ('fixed','flexible')),
  CHECK(isfinite(requested_start) AND isfinite(requested_end) AND requested_end > requested_start),
  CHECK(isfinite(earliest_start) AND isfinite(latest_finish) AND earliest_start <= requested_start AND requested_end <= latest_finish),
  CHECK(min_duration_minutes > 0 AND max_duration_minutes >= min_duration_minutes),
  CHECK(extract(epoch FROM requested_end-requested_start)/60 BETWEEN min_duration_minutes AND max_duration_minutes),
  CHECK(version > 0)
);

CREATE TABLE request_sectors (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  request_id uuid NOT NULL REFERENCES maintenance_requests(id) ON DELETE RESTRICT,
  sector_id uuid NOT NULL REFERENCES track_sectors(id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(request_id,sector_id)
);

CREATE TABLE request_workzones (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  request_id uuid NOT NULL REFERENCES maintenance_requests(id) ON DELETE RESTRICT,
  workzone_id uuid NOT NULL REFERENCES workzones(id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(request_id,workzone_id)
);

CREATE TABLE teams (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  department_id uuid NOT NULL REFERENCES departments(id) ON DELETE RESTRICT,
  name text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(department_id,name)
);

CREATE TABLE engineers (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  department_id uuid NOT NULL REFERENCES departments(id) ON DELETE RESTRICT,
  user_id uuid REFERENCES users(id) ON DELETE RESTRICT,
  employee_code text NOT NULL UNIQUE,
  name text NOT NULL,
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE skills (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code text NOT NULL UNIQUE,
  name text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE engineer_skills (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  engineer_id uuid NOT NULL REFERENCES engineers(id) ON DELETE RESTRICT,
  skill_id uuid NOT NULL REFERENCES skills(id) ON DELETE RESTRICT,
  starts_at timestamptz NOT NULL,
  ends_at timestamptz NOT NULL,
  period tstzrange GENERATED ALWAYS AS (tstzrange(starts_at, ends_at, '[)')) STORED,
  certificate_reference text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (isfinite(starts_at) AND isfinite(ends_at) AND ends_at > starts_at)
);

CREATE TABLE team_memberships (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  team_id uuid NOT NULL REFERENCES teams(id) ON DELETE RESTRICT,
  engineer_id uuid NOT NULL REFERENCES engineers(id) ON DELETE RESTRICT,
  starts_at timestamptz NOT NULL,
  ends_at timestamptz NOT NULL,
  period tstzrange GENERATED ALWAYS AS (tstzrange(starts_at, ends_at, '[)')) STORED,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (isfinite(starts_at) AND isfinite(ends_at) AND ends_at > starts_at)
);

CREATE TABLE shifts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  department_id uuid NOT NULL REFERENCES departments(id) ON DELETE RESTRICT,
  name text NOT NULL,
  starts_at timestamptz NOT NULL,
  ends_at timestamptz NOT NULL,
  period tstzrange GENERATED ALWAYS AS (tstzrange(starts_at, ends_at, '[)')) STORED,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (isfinite(starts_at) AND isfinite(ends_at) AND ends_at > starts_at)
);

CREATE TABLE engineer_availability (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  engineer_id uuid NOT NULL REFERENCES engineers(id) ON DELETE RESTRICT,
  shift_id uuid REFERENCES shifts(id) ON DELETE RESTRICT,
  available boolean NOT NULL,
  starts_at timestamptz NOT NULL,
  ends_at timestamptz NOT NULL,
  period tstzrange GENERATED ALWAYS AS (tstzrange(starts_at, ends_at, '[)')) STORED,
  reason text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (isfinite(starts_at) AND isfinite(ends_at) AND ends_at > starts_at)
);

CREATE TABLE team_availability (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  team_id uuid NOT NULL REFERENCES teams(id) ON DELETE RESTRICT,
  shift_id uuid REFERENCES shifts(id) ON DELETE RESTRICT,
  available boolean NOT NULL,
  starts_at timestamptz NOT NULL,
  ends_at timestamptz NOT NULL,
  period tstzrange GENERATED ALWAYS AS (tstzrange(starts_at, ends_at, '[)')) STORED,
  reason text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (isfinite(starts_at) AND isfinite(ends_at) AND ends_at > starts_at)
);

CREATE TABLE request_teams (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  request_id uuid NOT NULL REFERENCES maintenance_requests(id) ON DELETE RESTRICT,
  team_id uuid NOT NULL REFERENCES teams(id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(request_id,team_id)
);

CREATE TABLE request_engineers (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  request_id uuid NOT NULL REFERENCES maintenance_requests(id) ON DELETE RESTRICT,
  engineer_id uuid NOT NULL REFERENCES engineers(id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(request_id,engineer_id)
);

CREATE TABLE request_skills (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  request_id uuid NOT NULL REFERENCES maintenance_requests(id) ON DELETE RESTRICT,
  skill_id uuid NOT NULL REFERENCES skills(id) ON DELETE RESTRICT,
  required_count integer NOT NULL DEFAULT 1 CHECK(required_count > 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(request_id,skill_id)
);

CREATE TABLE equipment_types (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code text NOT NULL UNIQUE,
  name text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE equipment_assets (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  department_id uuid NOT NULL REFERENCES departments(id) ON DELETE RESTRICT,
  type_id uuid NOT NULL REFERENCES equipment_types(id) ON DELETE RESTRICT,
  asset_code text NOT NULL UNIQUE,
  name text NOT NULL,
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE equipment_capabilities (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code text NOT NULL UNIQUE,
  name text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE asset_capabilities (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  asset_id uuid NOT NULL REFERENCES equipment_assets(id) ON DELETE RESTRICT,
  capability_id uuid NOT NULL REFERENCES equipment_capabilities(id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(asset_id,capability_id)
);

CREATE TABLE equipment_availability (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  asset_id uuid NOT NULL REFERENCES equipment_assets(id) ON DELETE RESTRICT,
  available boolean NOT NULL,
  starts_at timestamptz NOT NULL,
  ends_at timestamptz NOT NULL,
  period tstzrange GENERATED ALWAYS AS (tstzrange(starts_at, ends_at, '[)')) STORED,
  reason text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (isfinite(starts_at) AND isfinite(ends_at) AND ends_at > starts_at)
);

CREATE TABLE request_equipment_requirements (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  request_id uuid NOT NULL REFERENCES maintenance_requests(id) ON DELETE RESTRICT,
  type_id uuid NOT NULL REFERENCES equipment_types(id) ON DELETE RESTRICT,
  quantity integer NOT NULL DEFAULT 1 CHECK(quantity > 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(request_id,type_id)
);

CREATE TABLE request_equipment_assets (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  request_id uuid NOT NULL REFERENCES maintenance_requests(id) ON DELETE RESTRICT,
  asset_id uuid NOT NULL REFERENCES equipment_assets(id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(request_id,asset_id)
);

CREATE TABLE request_capabilities (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  request_id uuid NOT NULL REFERENCES maintenance_requests(id) ON DELETE RESTRICT,
  capability_id uuid NOT NULL REFERENCES equipment_capabilities(id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(request_id,capability_id)
);

CREATE TABLE request_isolations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  request_id uuid NOT NULL REFERENCES maintenance_requests(id) ON DELETE RESTRICT,
  isolation_zone_id uuid NOT NULL REFERENCES isolation_zones(id) ON DELETE RESTRICT,
  required_state text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(request_id,isolation_zone_id),
  CHECK(required_state IN ('isolated','restored'))
);

CREATE TABLE compatibility_rules (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  first_work_type_id uuid NOT NULL REFERENCES work_types(id) ON DELETE RESTRICT,
  second_work_type_id uuid NOT NULL REFERENCES work_types(id) ON DELETE RESTRICT,
  compatible boolean NOT NULL,
  minimum_separation_metres numeric NOT NULL DEFAULT 0 CHECK(minimum_separation_metres >= 0),
  version integer NOT NULL DEFAULT 1,
  rationale text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(first_work_type_id,second_work_type_id,version),
  CHECK(first_work_type_id <= second_work_type_id)
);

CREATE TABLE rule_definitions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code text NOT NULL,
  version integer NOT NULL DEFAULT 1,
  name text NOT NULL,
  category text NOT NULL,
  severity text NOT NULL,
  blocking boolean NOT NULL DEFAULT true,
  enabled boolean NOT NULL DEFAULT true,
  parameters jsonb NOT NULL DEFAULT '{}',
  authority_reference text NOT NULL DEFAULT 'SYNTHETIC - not an operational rule',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(code,version),
  CHECK(severity IN ('information','low','medium','high','critical'))
);

CREATE TABLE dependency_types (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code text NOT NULL UNIQUE,
  name text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE request_dependencies (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  predecessor_id uuid NOT NULL REFERENCES maintenance_requests(id) ON DELETE RESTRICT,
  successor_id uuid NOT NULL REFERENCES maintenance_requests(id) ON DELETE RESTRICT,
  dependency_type_id uuid NOT NULL REFERENCES dependency_types(id) ON DELETE RESTRICT,
  lag_minutes integer NOT NULL DEFAULT 0 CHECK(lag_minutes >= 0),
  explanation text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(predecessor_id,successor_id,dependency_type_id),
  CHECK(predecessor_id <> successor_id)
);

CREATE TABLE travel_times (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  from_sector_id uuid NOT NULL REFERENCES track_sectors(id) ON DELETE RESTRICT,
  to_sector_id uuid NOT NULL REFERENCES track_sectors(id) ON DELETE RESTRICT,
  minutes integer NOT NULL CHECK(minutes >= 0),
  source text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(from_sector_id,to_sector_id)
);

CREATE TABLE optimisation_objectives (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code text NOT NULL UNIQUE,
  name text NOT NULL,
  weights jsonb NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE optimisation_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  window_id uuid NOT NULL REFERENCES engineering_windows(id) ON DELETE RESTRICT,
  objective_id uuid NOT NULL REFERENCES optimisation_objectives(id) ON DELETE RESTRICT,
  requested_by uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  status text NOT NULL DEFAULT 'queued',
  parameters jsonb NOT NULL DEFAULT '{}',
  input_snapshot jsonb NOT NULL,
  solver_version text,
  runtime_ms integer CHECK(runtime_ms >= 0),
  error_message text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK(status IN ('queued','running','feasible','optimal','infeasible','timed_out','failed'))
);

CREATE TABLE scenarios (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id uuid NOT NULL REFERENCES optimisation_runs(id) ON DELETE RESTRICT,
  name text NOT NULL,
  status text NOT NULL DEFAULT 'draft',
  version integer NOT NULL DEFAULT 1,
  validation_status text NOT NULL DEFAULT 'unvalidated',
  provenance text NOT NULL DEFAULT 'solver',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK(status IN ('draft','pending_review','approved','rejected','superseded','withdrawn')),
  CHECK(validation_status IN ('unvalidated','valid','invalid')),
  CHECK(version > 0)
);

CREATE TABLE scenario_assignments (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  scenario_id uuid NOT NULL REFERENCES scenarios(id) ON DELETE RESTRICT,
  request_id uuid NOT NULL REFERENCES maintenance_requests(id) ON DELETE RESTRICT,
  request_version integer NOT NULL CHECK(request_version>0),
  original_start timestamptz NOT NULL,
  original_end timestamptz NOT NULL,
  starts_at timestamptz NOT NULL,
  ends_at timestamptz NOT NULL,
  period tstzrange GENERATED ALWAYS AS (tstzrange(starts_at, ends_at, '[)')) STORED,
  reason text NOT NULL,
  feasible boolean NOT NULL DEFAULT false,
  locked boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(scenario_id,request_id),
  CHECK(original_end>original_start),
  CHECK (isfinite(starts_at) AND isfinite(ends_at) AND ends_at > starts_at)
);

CREATE TABLE scenario_sectors (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  assignment_id uuid NOT NULL REFERENCES scenario_assignments(id) ON DELETE RESTRICT,
  sector_id uuid NOT NULL REFERENCES track_sectors(id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(assignment_id,sector_id)
);

CREATE TABLE scenario_teams (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  assignment_id uuid NOT NULL REFERENCES scenario_assignments(id) ON DELETE RESTRICT,
  team_id uuid NOT NULL REFERENCES teams(id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(assignment_id,team_id)
);

CREATE TABLE scenario_engineers (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  assignment_id uuid NOT NULL REFERENCES scenario_assignments(id) ON DELETE RESTRICT,
  engineer_id uuid NOT NULL REFERENCES engineers(id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(assignment_id,engineer_id)
);

CREATE TABLE scenario_equipment (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  assignment_id uuid NOT NULL REFERENCES scenario_assignments(id) ON DELETE RESTRICT,
  asset_id uuid NOT NULL REFERENCES equipment_assets(id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(assignment_id,asset_id)
);

CREATE TABLE possessions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  scenario_id uuid NOT NULL REFERENCES scenarios(id) ON DELETE RESTRICT,
  code text NOT NULL,
  exclusive boolean NOT NULL DEFAULT true,
  starts_at timestamptz NOT NULL,
  ends_at timestamptz NOT NULL,
  period tstzrange GENERATED ALWAYS AS (tstzrange(starts_at, ends_at, '[)')) STORED,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (isfinite(starts_at) AND isfinite(ends_at) AND ends_at > starts_at),
  UNIQUE(scenario_id,code)
);

CREATE TABLE possession_sectors (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  possession_id uuid NOT NULL REFERENCES possessions(id) ON DELETE RESTRICT,
  sector_id uuid NOT NULL REFERENCES track_sectors(id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(possession_id,sector_id)
);

CREATE TABLE possession_assignments (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  possession_id uuid NOT NULL REFERENCES possessions(id) ON DELETE RESTRICT,
  assignment_id uuid NOT NULL REFERENCES scenario_assignments(id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(possession_id,assignment_id)
);

CREATE TABLE isolation_plans (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  scenario_id uuid NOT NULL REFERENCES scenarios(id) ON DELETE RESTRICT,
  isolation_zone_id uuid NOT NULL REFERENCES isolation_zones(id) ON DELETE RESTRICT,
  starts_at timestamptz NOT NULL,
  ends_at timestamptz NOT NULL,
  period tstzrange GENERATED ALWAYS AS (tstzrange(starts_at, ends_at, '[)')) STORED,
  restored_at timestamptz NOT NULL,
  handback_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (isfinite(starts_at) AND isfinite(ends_at) AND ends_at > starts_at),
  CHECK(restored_at>=ends_at AND handback_at>=restored_at)
);

CREATE TABLE scenario_metrics (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  scenario_id uuid NOT NULL REFERENCES scenarios(id) ON DELETE RESTRICT,
  conflicts_resolved integer NOT NULL DEFAULT 0 CHECK(conflicts_resolved>=0),
  unresolved_conflicts integer NOT NULL DEFAULT 0 CHECK(unresolved_conflicts>=0),
  requests_moved integer NOT NULL DEFAULT 0 CHECK(requests_moved>=0),
  total_movement_minutes numeric NOT NULL DEFAULT 0 CHECK(total_movement_minutes>=0),
  possession_count integer NOT NULL DEFAULT 0 CHECK(possession_count>=0),
  disruption_score numeric CHECK(disruption_score>=0),
  resource_utilisation numeric CHECK(resource_utilisation BETWEEN 0 AND 1),
  unscheduled_requests integer NOT NULL DEFAULT 0 CHECK(unscheduled_requests>=0),
  solver_status text NOT NULL,
  solver_runtime_ms integer CHECK(solver_runtime_ms>=0),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(scenario_id)
);

CREATE TABLE scoring_policies (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code text NOT NULL,
  version integer NOT NULL,
  weights jsonb NOT NULL,
  is_validated boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(code,version)
);

CREATE TABLE analysis_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  window_id uuid NOT NULL REFERENCES engineering_windows(id) ON DELETE RESTRICT,
  scenario_id uuid REFERENCES scenarios(id) ON DELETE RESTRICT,
  requested_by uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  scoring_policy_id uuid REFERENCES scoring_policies(id) ON DELETE RESTRICT,
  status text NOT NULL DEFAULT 'queued',
  input_snapshot jsonb NOT NULL,
  rule_snapshot jsonb NOT NULL,
  completed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK(status IN ('queued','running','completed','failed'))
);

CREATE TABLE conflicts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  conflict_code text NOT NULL UNIQUE DEFAULT ('CF-' || lpad(nextval('conflict_code_seq')::text,6,'0')),
  analysis_run_id uuid NOT NULL REFERENCES analysis_runs(id) ON DELETE RESTRICT,
  rule_id uuid NOT NULL REFERENCES rule_definitions(id) ON DELETE RESTRICT,
  title text NOT NULL,
  explanation text NOT NULL,
  severity text NOT NULL,
  risk_score numeric CHECK(risk_score BETWEEN 0 AND 100),
  resolution_status text NOT NULL DEFAULT 'open',
  resolution_notes text,
  detection_method text NOT NULL DEFAULT 'automatic',
  detected_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK(severity IN ('information','low','medium','high','critical')),
  CHECK(resolution_status IN ('open','resolved','dismissed')),
  CHECK(detection_method IN ('automatic','manual','synthetic'))
);

CREATE TABLE conflict_requests (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  conflict_id uuid NOT NULL REFERENCES conflicts(id) ON DELETE RESTRICT,
  request_id uuid NOT NULL REFERENCES maintenance_requests(id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(conflict_id,request_id)
);

CREATE TABLE conflict_teams (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  conflict_id uuid NOT NULL REFERENCES conflicts(id) ON DELETE RESTRICT,
  team_id uuid NOT NULL REFERENCES teams(id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(conflict_id,team_id)
);

CREATE TABLE conflict_engineers (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  conflict_id uuid NOT NULL REFERENCES conflicts(id) ON DELETE RESTRICT,
  engineer_id uuid NOT NULL REFERENCES engineers(id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(conflict_id,engineer_id)
);

CREATE TABLE conflict_equipment (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  conflict_id uuid NOT NULL REFERENCES conflicts(id) ON DELETE RESTRICT,
  asset_id uuid NOT NULL REFERENCES equipment_assets(id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(conflict_id,asset_id)
);

CREATE TABLE conflict_sectors (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  conflict_id uuid NOT NULL REFERENCES conflicts(id) ON DELETE RESTRICT,
  sector_id uuid NOT NULL REFERENCES track_sectors(id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(conflict_id,sector_id)
);

CREATE TABLE conflict_isolations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  conflict_id uuid NOT NULL REFERENCES conflicts(id) ON DELETE RESTRICT,
  isolation_zone_id uuid NOT NULL REFERENCES isolation_zones(id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(conflict_id,isolation_zone_id)
);

CREATE TABLE conflict_score_components (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  conflict_id uuid NOT NULL REFERENCES conflicts(id) ON DELETE RESTRICT,
  component text NOT NULL,
  score numeric NOT NULL CHECK(score BETWEEN 0 AND 100),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(conflict_id,component),
  CHECK(component IN ('safety','operational','resource','urgency','passenger'))
);

CREATE TABLE request_locks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  request_id uuid NOT NULL REFERENCES maintenance_requests(id) ON DELETE RESTRICT,
  scenario_id uuid REFERENCES scenarios(id) ON DELETE RESTRICT,
  locked_by uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  scope text NOT NULL,
  reason text NOT NULL,
  locked_values jsonb NOT NULL,
  expires_at timestamptz,
  released_at timestamptz,
  released_by uuid REFERENCES users(id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK(scope IN ('request','scenario')),
  CHECK((scope='request' AND scenario_id IS NULL) OR (scope='scenario' AND scenario_id IS NOT NULL)),
  CHECK(expires_at IS NULL OR expires_at>created_at),
  CHECK(released_at IS NULL OR released_at>=created_at)
);

CREATE TABLE lock_fields (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  lock_id uuid NOT NULL REFERENCES request_locks(id) ON DELETE RESTRICT,
  field text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(lock_id,field),
  CHECK(field IN ('timing','team','engineers','equipment','sectors'))
);

CREATE TABLE approval_workflows (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  operator_id uuid NOT NULL REFERENCES operators(id) ON DELETE RESTRICT,
  name text NOT NULL,
  version integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(operator_id,name,version)
);

CREATE TABLE approval_stages (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  workflow_id uuid NOT NULL REFERENCES approval_workflows(id) ON DELETE RESTRICT,
  required_role_id uuid NOT NULL REFERENCES roles(id) ON DELETE RESTRICT,
  sequence_no integer NOT NULL CHECK(sequence_no>0),
  name text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(workflow_id,sequence_no)
);

CREATE TABLE approval_requests (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  scenario_id uuid NOT NULL REFERENCES scenarios(id) ON DELETE RESTRICT,
  workflow_id uuid NOT NULL REFERENCES approval_workflows(id) ON DELETE RESTRICT,
  submitted_by uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  scenario_version integer NOT NULL,
  status text NOT NULL DEFAULT 'pending_review',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK(status IN ('pending_review','approved','rejected','withdrawn'))
);

CREATE TABLE approval_decisions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  approval_request_id uuid NOT NULL REFERENCES approval_requests(id) ON DELETE RESTRICT,
  stage_id uuid NOT NULL REFERENCES approval_stages(id) ON DELETE RESTRICT,
  approver_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  decision text NOT NULL,
  comment text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(approval_request_id,stage_id),
  CHECK(decision IN ('approved','rejected'))
);

CREATE TABLE schedule_versions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  window_id uuid NOT NULL REFERENCES engineering_windows(id) ON DELETE RESTRICT,
  scenario_id uuid NOT NULL REFERENCES scenarios(id) ON DELETE RESTRICT,
  approval_request_id uuid NOT NULL REFERENCES approval_requests(id) ON DELETE RESTRICT,
  approved_by uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  version_no integer NOT NULL CHECK(version_no>0),
  snapshot jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(window_id,version_no),
  UNIQUE(approval_request_id)
);

CREATE TABLE active_schedules (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  window_id uuid NOT NULL REFERENCES engineering_windows(id) ON DELETE RESTRICT,
  schedule_version_id uuid NOT NULL REFERENCES schedule_versions(id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(window_id),
  UNIQUE(schedule_version_id)
);

CREATE TABLE audit_logs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  actor_id uuid REFERENCES users(id) ON DELETE RESTRICT,
  action text NOT NULL,
  entity_type text NOT NULL,
  entity_id uuid NOT NULL,
  before_state jsonb,
  after_state jsonb,
  correlation_id uuid,
  source text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE activity_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  actor_id uuid REFERENCES users(id) ON DELETE RESTRICT,
  event_type text NOT NULL,
  message text NOT NULL,
  entity_type text,
  entity_id uuid,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE event_reads (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id uuid NOT NULL REFERENCES activity_events(id) ON DELETE RESTRICT,
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  read_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(event_id,user_id)
);

CREATE TABLE copilot_conversations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  title text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE copilot_messages (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id uuid NOT NULL REFERENCES copilot_conversations(id) ON DELETE RESTRICT,
  role text NOT NULL,
  content text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK(role IN ('user','assistant','tool'))
);

CREATE TABLE copilot_tool_calls (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  message_id uuid NOT NULL REFERENCES copilot_messages(id) ON DELETE RESTRICT,
  actor_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  tool_name text NOT NULL,
  arguments jsonb NOT NULL,
  result jsonb,
  status text NOT NULL,
  correlation_id uuid NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK(status IN ('pending','succeeded','failed','denied'))
);

CREATE TABLE copilot_request_refs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  message_id uuid NOT NULL REFERENCES copilot_messages(id) ON DELETE RESTRICT,
  request_id uuid NOT NULL REFERENCES maintenance_requests(id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(message_id,request_id)
);

CREATE TABLE copilot_conflict_refs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  message_id uuid NOT NULL REFERENCES copilot_messages(id) ON DELETE RESTRICT,
  conflict_id uuid NOT NULL REFERENCES conflicts(id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(message_id,conflict_id)
);

CREATE TABLE copilot_scenario_refs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  message_id uuid NOT NULL REFERENCES copilot_messages(id) ON DELETE RESTRICT,
  scenario_id uuid NOT NULL REFERENCES scenarios(id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(message_id,scenario_id)
);

-- Foreign-key and spatial/range indexes, including reverse junction lookups.
CREATE INDEX ix_departments_operator_id ON departments (operator_id);
CREATE INDEX ix_users_department_id ON users (department_id);
CREATE INDEX ix_user_roles_user_id ON user_roles (user_id);
CREATE INDEX ix_user_roles_role_id ON user_roles (role_id);
CREATE INDEX ix_networks_operator_id ON networks (operator_id);
CREATE INDEX ix_lines_network_id ON lines (network_id);
CREATE INDEX ix_stations_network_id ON stations (network_id);
CREATE INDEX ix_stations_geom ON stations USING gist (geom);
CREATE INDEX ix_line_stations_line_id ON line_stations (line_id);
CREATE INDEX ix_line_stations_station_id ON line_stations (station_id);
CREATE INDEX ix_track_sectors_line_id ON track_sectors (line_id);
CREATE INDEX ix_track_sectors_from_station_id ON track_sectors (from_station_id);
CREATE INDEX ix_track_sectors_to_station_id ON track_sectors (to_station_id);
CREATE INDEX ix_track_sectors_geom ON track_sectors USING gist (geom);
CREATE INDEX ix_tracks_sector_id ON tracks (sector_id);
CREATE INDEX ix_track_segments_track_id ON track_segments (track_id);
CREATE INDEX ix_track_segments_geom ON track_segments USING gist (geom);
CREATE INDEX ix_workzones_network_id ON workzones (network_id);
CREATE INDEX ix_workzones_geom ON workzones USING gist (geom);
CREATE INDEX ix_workzone_sectors_workzone_id ON workzone_sectors (workzone_id);
CREATE INDEX ix_workzone_sectors_sector_id ON workzone_sectors (sector_id);
CREATE INDEX ix_isolation_zones_network_id ON isolation_zones (network_id);
CREATE INDEX ix_isolation_zones_geom ON isolation_zones USING gist (geom);
CREATE INDEX ix_isolation_zone_sectors_isolation_zone_id ON isolation_zone_sectors (isolation_zone_id);
CREATE INDEX ix_isolation_zone_sectors_sector_id ON isolation_zone_sectors (sector_id);
CREATE INDEX ix_engineering_windows_line_id ON engineering_windows (line_id);
CREATE INDEX ix_engineering_windows_period ON engineering_windows USING gist (period);
CREATE INDEX ix_window_periods_window_id ON window_periods (window_id);
CREATE INDEX ix_window_periods_period ON window_periods USING gist (period);
CREATE INDEX ix_sector_availability_window_id ON sector_availability (window_id);
CREATE INDEX ix_sector_availability_sector_id ON sector_availability (sector_id);
CREATE INDEX ix_sector_availability_period ON sector_availability USING gist (period);
CREATE INDEX ix_maintenance_requests_window_id ON maintenance_requests (window_id);
CREATE INDEX ix_maintenance_requests_department_id ON maintenance_requests (department_id);
CREATE INDEX ix_maintenance_requests_work_type_id ON maintenance_requests (work_type_id);
CREATE INDEX ix_maintenance_requests_requested_period ON maintenance_requests USING gist (requested_period);
CREATE INDEX ix_maintenance_requests_created_by ON maintenance_requests (created_by);
CREATE INDEX ix_maintenance_requests_submitted_by ON maintenance_requests (submitted_by);
CREATE INDEX ix_request_sectors_request_id ON request_sectors (request_id);
CREATE INDEX ix_request_sectors_sector_id ON request_sectors (sector_id);
CREATE INDEX ix_request_workzones_request_id ON request_workzones (request_id);
CREATE INDEX ix_request_workzones_workzone_id ON request_workzones (workzone_id);
CREATE INDEX ix_teams_department_id ON teams (department_id);
CREATE INDEX ix_engineers_department_id ON engineers (department_id);
CREATE INDEX ix_engineers_user_id ON engineers (user_id);
CREATE INDEX ix_engineer_skills_engineer_id ON engineer_skills (engineer_id);
CREATE INDEX ix_engineer_skills_skill_id ON engineer_skills (skill_id);
CREATE INDEX ix_engineer_skills_period ON engineer_skills USING gist (period);
CREATE INDEX ix_team_memberships_team_id ON team_memberships (team_id);
CREATE INDEX ix_team_memberships_engineer_id ON team_memberships (engineer_id);
CREATE INDEX ix_team_memberships_period ON team_memberships USING gist (period);
CREATE INDEX ix_shifts_department_id ON shifts (department_id);
CREATE INDEX ix_shifts_period ON shifts USING gist (period);
CREATE INDEX ix_engineer_availability_engineer_id ON engineer_availability (engineer_id);
CREATE INDEX ix_engineer_availability_shift_id ON engineer_availability (shift_id);
CREATE INDEX ix_engineer_availability_period ON engineer_availability USING gist (period);
CREATE INDEX ix_team_availability_team_id ON team_availability (team_id);
CREATE INDEX ix_team_availability_shift_id ON team_availability (shift_id);
CREATE INDEX ix_team_availability_period ON team_availability USING gist (period);
CREATE INDEX ix_request_teams_request_id ON request_teams (request_id);
CREATE INDEX ix_request_teams_team_id ON request_teams (team_id);
CREATE INDEX ix_request_engineers_request_id ON request_engineers (request_id);
CREATE INDEX ix_request_engineers_engineer_id ON request_engineers (engineer_id);
CREATE INDEX ix_request_skills_request_id ON request_skills (request_id);
CREATE INDEX ix_request_skills_skill_id ON request_skills (skill_id);
CREATE INDEX ix_equipment_assets_department_id ON equipment_assets (department_id);
CREATE INDEX ix_equipment_assets_type_id ON equipment_assets (type_id);
CREATE INDEX ix_asset_capabilities_asset_id ON asset_capabilities (asset_id);
CREATE INDEX ix_asset_capabilities_capability_id ON asset_capabilities (capability_id);
CREATE INDEX ix_equipment_availability_asset_id ON equipment_availability (asset_id);
CREATE INDEX ix_equipment_availability_period ON equipment_availability USING gist (period);
CREATE INDEX ix_request_equipment_requirements_request_id ON request_equipment_requirements (request_id);
CREATE INDEX ix_request_equipment_requirements_type_id ON request_equipment_requirements (type_id);
CREATE INDEX ix_request_equipment_assets_request_id ON request_equipment_assets (request_id);
CREATE INDEX ix_request_equipment_assets_asset_id ON request_equipment_assets (asset_id);
CREATE INDEX ix_request_capabilities_request_id ON request_capabilities (request_id);
CREATE INDEX ix_request_capabilities_capability_id ON request_capabilities (capability_id);
CREATE INDEX ix_request_isolations_request_id ON request_isolations (request_id);
CREATE INDEX ix_request_isolations_isolation_zone_id ON request_isolations (isolation_zone_id);
CREATE INDEX ix_compatibility_rules_first_work_type_id ON compatibility_rules (first_work_type_id);
CREATE INDEX ix_compatibility_rules_second_work_type_id ON compatibility_rules (second_work_type_id);
CREATE INDEX ix_request_dependencies_predecessor_id ON request_dependencies (predecessor_id);
CREATE INDEX ix_request_dependencies_successor_id ON request_dependencies (successor_id);
CREATE INDEX ix_request_dependencies_dependency_type_id ON request_dependencies (dependency_type_id);
CREATE INDEX ix_travel_times_from_sector_id ON travel_times (from_sector_id);
CREATE INDEX ix_travel_times_to_sector_id ON travel_times (to_sector_id);
CREATE INDEX ix_optimisation_runs_window_id ON optimisation_runs (window_id);
CREATE INDEX ix_optimisation_runs_objective_id ON optimisation_runs (objective_id);
CREATE INDEX ix_optimisation_runs_requested_by ON optimisation_runs (requested_by);
CREATE INDEX ix_scenarios_run_id ON scenarios (run_id);
CREATE INDEX ix_scenario_assignments_scenario_id ON scenario_assignments (scenario_id);
CREATE INDEX ix_scenario_assignments_request_id ON scenario_assignments (request_id);
CREATE INDEX ix_scenario_assignments_period ON scenario_assignments USING gist (period);
CREATE INDEX ix_scenario_sectors_assignment_id ON scenario_sectors (assignment_id);
CREATE INDEX ix_scenario_sectors_sector_id ON scenario_sectors (sector_id);
CREATE INDEX ix_scenario_teams_assignment_id ON scenario_teams (assignment_id);
CREATE INDEX ix_scenario_teams_team_id ON scenario_teams (team_id);
CREATE INDEX ix_scenario_engineers_assignment_id ON scenario_engineers (assignment_id);
CREATE INDEX ix_scenario_engineers_engineer_id ON scenario_engineers (engineer_id);
CREATE INDEX ix_scenario_equipment_assignment_id ON scenario_equipment (assignment_id);
CREATE INDEX ix_scenario_equipment_asset_id ON scenario_equipment (asset_id);
CREATE INDEX ix_possessions_scenario_id ON possessions (scenario_id);
CREATE INDEX ix_possessions_period ON possessions USING gist (period);
CREATE INDEX ix_possession_sectors_possession_id ON possession_sectors (possession_id);
CREATE INDEX ix_possession_sectors_sector_id ON possession_sectors (sector_id);
CREATE INDEX ix_possession_assignments_possession_id ON possession_assignments (possession_id);
CREATE INDEX ix_possession_assignments_assignment_id ON possession_assignments (assignment_id);
CREATE INDEX ix_isolation_plans_scenario_id ON isolation_plans (scenario_id);
CREATE INDEX ix_isolation_plans_isolation_zone_id ON isolation_plans (isolation_zone_id);
CREATE INDEX ix_isolation_plans_period ON isolation_plans USING gist (period);
CREATE INDEX ix_scenario_metrics_scenario_id ON scenario_metrics (scenario_id);
CREATE INDEX ix_analysis_runs_window_id ON analysis_runs (window_id);
CREATE INDEX ix_analysis_runs_scenario_id ON analysis_runs (scenario_id);
CREATE INDEX ix_analysis_runs_requested_by ON analysis_runs (requested_by);
CREATE INDEX ix_analysis_runs_scoring_policy_id ON analysis_runs (scoring_policy_id);
CREATE INDEX ix_conflicts_analysis_run_id ON conflicts (analysis_run_id);
CREATE INDEX ix_conflicts_rule_id ON conflicts (rule_id);
CREATE INDEX ix_conflict_requests_conflict_id ON conflict_requests (conflict_id);
CREATE INDEX ix_conflict_requests_request_id ON conflict_requests (request_id);
CREATE INDEX ix_conflict_teams_conflict_id ON conflict_teams (conflict_id);
CREATE INDEX ix_conflict_teams_team_id ON conflict_teams (team_id);
CREATE INDEX ix_conflict_engineers_conflict_id ON conflict_engineers (conflict_id);
CREATE INDEX ix_conflict_engineers_engineer_id ON conflict_engineers (engineer_id);
CREATE INDEX ix_conflict_equipment_conflict_id ON conflict_equipment (conflict_id);
CREATE INDEX ix_conflict_equipment_asset_id ON conflict_equipment (asset_id);
CREATE INDEX ix_conflict_sectors_conflict_id ON conflict_sectors (conflict_id);
CREATE INDEX ix_conflict_sectors_sector_id ON conflict_sectors (sector_id);
CREATE INDEX ix_conflict_isolations_conflict_id ON conflict_isolations (conflict_id);
CREATE INDEX ix_conflict_isolations_isolation_zone_id ON conflict_isolations (isolation_zone_id);
CREATE INDEX ix_conflict_score_components_conflict_id ON conflict_score_components (conflict_id);
CREATE INDEX ix_request_locks_request_id ON request_locks (request_id);
CREATE INDEX ix_request_locks_scenario_id ON request_locks (scenario_id);
CREATE INDEX ix_request_locks_locked_by ON request_locks (locked_by);
CREATE INDEX ix_request_locks_released_by ON request_locks (released_by);
CREATE INDEX ix_lock_fields_lock_id ON lock_fields (lock_id);
CREATE INDEX ix_approval_workflows_operator_id ON approval_workflows (operator_id);
CREATE INDEX ix_approval_stages_workflow_id ON approval_stages (workflow_id);
CREATE INDEX ix_approval_stages_required_role_id ON approval_stages (required_role_id);
CREATE INDEX ix_approval_requests_scenario_id ON approval_requests (scenario_id);
CREATE INDEX ix_approval_requests_workflow_id ON approval_requests (workflow_id);
CREATE INDEX ix_approval_requests_submitted_by ON approval_requests (submitted_by);
CREATE INDEX ix_approval_decisions_approval_request_id ON approval_decisions (approval_request_id);
CREATE INDEX ix_approval_decisions_stage_id ON approval_decisions (stage_id);
CREATE INDEX ix_approval_decisions_approver_id ON approval_decisions (approver_id);
CREATE INDEX ix_schedule_versions_window_id ON schedule_versions (window_id);
CREATE INDEX ix_schedule_versions_scenario_id ON schedule_versions (scenario_id);
CREATE INDEX ix_schedule_versions_approval_request_id ON schedule_versions (approval_request_id);
CREATE INDEX ix_schedule_versions_approved_by ON schedule_versions (approved_by);
CREATE INDEX ix_active_schedules_window_id ON active_schedules (window_id);
CREATE INDEX ix_active_schedules_schedule_version_id ON active_schedules (schedule_version_id);
CREATE INDEX ix_audit_logs_actor_id ON audit_logs (actor_id);
CREATE INDEX ix_activity_events_actor_id ON activity_events (actor_id);
CREATE INDEX ix_event_reads_event_id ON event_reads (event_id);
CREATE INDEX ix_event_reads_user_id ON event_reads (user_id);
CREATE INDEX ix_copilot_conversations_user_id ON copilot_conversations (user_id);
CREATE INDEX ix_copilot_messages_conversation_id ON copilot_messages (conversation_id);
CREATE INDEX ix_copilot_tool_calls_message_id ON copilot_tool_calls (message_id);
CREATE INDEX ix_copilot_tool_calls_actor_id ON copilot_tool_calls (actor_id);
CREATE INDEX ix_copilot_request_refs_message_id ON copilot_request_refs (message_id);
CREATE INDEX ix_copilot_request_refs_request_id ON copilot_request_refs (request_id);
CREATE INDEX ix_copilot_conflict_refs_message_id ON copilot_conflict_refs (message_id);
CREATE INDEX ix_copilot_conflict_refs_conflict_id ON copilot_conflict_refs (conflict_id);
CREATE INDEX ix_copilot_scenario_refs_message_id ON copilot_scenario_refs (message_id);
CREATE INDEX ix_copilot_scenario_refs_scenario_id ON copilot_scenario_refs (scenario_id);
CREATE INDEX ix_request_status ON maintenance_requests(status_code);
CREATE INDEX ix_request_start ON maintenance_requests(requested_start);
CREATE INDEX ix_activity_created ON activity_events(created_at DESC);
CREATE INDEX ix_conflict_status ON conflicts(resolution_status,severity);
CREATE INDEX ix_audit_entity ON audit_logs(entity_type,entity_id,created_at);
CREATE UNIQUE INDEX one_pending_approval ON approval_requests(scenario_id) WHERE status='pending_review';
COMMENT ON TABLE maintenance_requests IS 'Requested intent, never overwritten by a proposed schedule. Conflicting requests are allowed.';
COMMENT ON TABLE schedule_versions IS 'Immutable approval-time snapshot; active_schedules is the independently mutable pointer.';
COMMENT ON COLUMN stations.geom IS 'WGS84 longitude/latitude; NULL when unverified. Never use schematic screen coordinates.';
COMMENT ON TABLE conflicts IS 'Safety blocking comes from rule_definitions.blocking, never from a weighted score.';
