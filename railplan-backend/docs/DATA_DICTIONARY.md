# Data dictionary

## Scenario B/C optimisation fields

`scenario` is A/B/C; `eclo` is 0/1; `physical_night` is a network-wide weekly slot; `access_night` is local to contract/activity-type/week; `co_share_group` is local to location/week. Scenario B uses `7×excess_access_nights_total + 5×eclo_nights_total`. Scenario C uses `priority_weighted_overrun + 7×excess_access_nights_total + 5×eclo_nights_total`, caps each location/week excess at one, and retains Alpha/Beta window active/start/end/activity IDs plus cross-line ECLO activity IDs in the immutable result JSON. Required, delivered, standard/ECLO contribution, and over-delivery are also retained there.

## PS1 optimiser additions: migration 0007

Five dedicated tables: `ps1_optimisation_runs`, `ps1_optimisation_accesses`,
`ps1_optimisation_occupancies`, `ps1_optimisation_contract_results`, `ps1_optimisation_keys`.
The run retains exact versioned result/validation/configuration/request/diagnostic JSONB,
accepted CSV strings, canonical child manifest and creating transaction ID. Child rows and
key references have composite operator/instance ownership. Score/bound/gap are NUMERIC;
gap is a fraction rounded to 12 decimals. Per-contract weighted_overrun is nullable and
left NULL; raw overrun is never substituted. See SQL 010 and
[the complete schema/field guide](PS1_OPTIMISATION_PERSISTENCE.md#schema-and-sealing).

## PS1 additions: migration 0006

SQL authority: `sql/009_ps1_validations.sql`; previous instance storage is in
`sql/008_ps1_instances.sql`. Every new table is immutable under UPDATE/DELETE/TRUNCATE
and has an INSERT audit trigger. All IDs are UUIDs, hashes are SHA-256 hex text.

| Table | Columns | Keys and purpose |
|---|---|---|
| ps1_validation_runs | id, instance_id, operator_id, created_by, scenario, dataset_fingerprint, submission_fingerprint, validator_version, source_files, policy_snapshot, result_snapshot, created_at | Unique instance/submission/version; composite instance/operator FK; exact CSV strings and immutable JSONB evidence |
| ps1_validation_violations | id, validation_id, operator_id, ordinal, rule_code, evidence_snapshot, created_at | Unique run/ordinal; composite run/operator FK; structured violation JSONB, ordered/filterable |
| ps1_validation_keys | id, operator_id, idempotency_key, request_fingerprint, validation_id, created_at | Unique operator/key; composite run/operator FK; retains deduplication aliases and collision evidence |

`source_files` maps exact filenames to exact submitted strings. `policy_snapshot` is the
frozen active rule-policy JSON; `result_snapshot` is the full typed report. `ordinal` is
zero-based stable report order. `evidence_snapshot` contains code/message/week/IDs/group/
evidence. `created_at` is timestamptz with `clock_timestamp()`. Creator references users;
operators and immutable parents use restricted deletion. Null eligible objectives are
stored inside the result JSON, not coerced to zero. No legacy conflict severity is stored.

SQL is authoritative. Every table has a database-generated UUID key and created_at; mutable tables also have updated_at. Foreign keys use ON DELETE RESTRICT. Table-specific constraints follow each inventory.

## operators

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| code | `text NOT NULL UNIQUE` |
| name | `text NOT NULL` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

## departments

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| operator_id | `uuid NOT NULL REFERENCES operators(id) ON DELETE RESTRICT` |
| name | `text NOT NULL` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `UNIQUE(operator_id,name)`.

## users

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| department_id | `uuid NOT NULL REFERENCES departments(id) ON DELETE RESTRICT` |
| auth_subject | `text NOT NULL UNIQUE` |
| display_name | `text NOT NULL` |
| active | `boolean NOT NULL DEFAULT true` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

## roles

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| code | `text NOT NULL UNIQUE` |
| name | `text NOT NULL` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

## user_roles

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| user_id | `uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT` |
| role_id | `uuid NOT NULL REFERENCES roles(id) ON DELETE RESTRICT` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `UNIQUE(user_id,role_id)`.

## networks

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| operator_id | `uuid NOT NULL REFERENCES operators(id) ON DELETE RESTRICT` |
| code | `text NOT NULL UNIQUE` |
| name | `text NOT NULL` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

## lines

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| network_id | `uuid NOT NULL REFERENCES networks(id) ON DELETE RESTRICT` |
| code | `text NOT NULL UNIQUE` |
| name | `text NOT NULL` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

## stations

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| network_id | `uuid NOT NULL REFERENCES networks(id) ON DELETE RESTRICT` |
| name | `text NOT NULL` |
| geom | `geometry(Point,4326)` |
| geometry_source | `text NOT NULL DEFAULT 'unverified'` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

## line_stations

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| line_id | `uuid NOT NULL REFERENCES lines(id) ON DELETE RESTRICT` |
| station_id | `uuid NOT NULL REFERENCES stations(id) ON DELETE RESTRICT` |
| code | `text NOT NULL UNIQUE` |
| sequence_no | `integer NOT NULL` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `UNIQUE(line_id,station_id)`; `UNIQUE(line_id,sequence_no)`.

## track_sectors

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| line_id | `uuid NOT NULL REFERENCES lines(id) ON DELETE RESTRICT` |
| from_station_id | `uuid NOT NULL REFERENCES stations(id) ON DELETE RESTRICT` |
| to_station_id | `uuid NOT NULL REFERENCES stations(id) ON DELETE RESTRICT` |
| code | `text NOT NULL UNIQUE` |
| name | `text NOT NULL` |
| geom | `geometry(MultiLineString,4326)` |
| geometry_source | `text NOT NULL DEFAULT 'unverified'` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `CHECK(from_station_id <> to_station_id)`.

## tracks

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| sector_id | `uuid NOT NULL REFERENCES track_sectors(id) ON DELETE RESTRICT` |
| code | `text NOT NULL` |
| direction | `text NOT NULL` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `UNIQUE(sector_id,code)`.

## track_segments

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| track_id | `uuid NOT NULL REFERENCES tracks(id) ON DELETE RESTRICT` |
| code | `text NOT NULL UNIQUE` |
| geom | `geometry(LineString,4326)` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

## workzones

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| network_id | `uuid NOT NULL REFERENCES networks(id) ON DELETE RESTRICT` |
| code | `text NOT NULL UNIQUE` |
| name | `text NOT NULL` |
| geom | `geometry(MultiPolygon,4326)` |
| geometry_source | `text NOT NULL DEFAULT 'unverified'` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `CHECK(geom IS NULL OR ST_IsValid(geom))`.

## workzone_sectors

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| workzone_id | `uuid NOT NULL REFERENCES workzones(id) ON DELETE RESTRICT` |
| sector_id | `uuid NOT NULL REFERENCES track_sectors(id) ON DELETE RESTRICT` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `UNIQUE(workzone_id,sector_id)`.

## isolation_zones

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| network_id | `uuid NOT NULL REFERENCES networks(id) ON DELETE RESTRICT` |
| code | `text NOT NULL UNIQUE` |
| name | `text NOT NULL` |
| geom | `geometry(MultiPolygon,4326)` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

## isolation_zone_sectors

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| isolation_zone_id | `uuid NOT NULL REFERENCES isolation_zones(id) ON DELETE RESTRICT` |
| sector_id | `uuid NOT NULL REFERENCES track_sectors(id) ON DELETE RESTRICT` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `UNIQUE(isolation_zone_id,sector_id)`.

## engineering_windows

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| line_id | `uuid NOT NULL REFERENCES lines(id) ON DELETE RESTRICT` |
| name | `text NOT NULL` |
| service_date | `date NOT NULL` |
| timezone | `text NOT NULL DEFAULT 'Asia/Singapore'` |
| starts_at | `timestamptz NOT NULL` |
| ends_at | `timestamptz NOT NULL` |
| period | `tstzrange GENERATED ALWAYS AS (tstzrange(starts_at, ends_at, '[)')) STORED` |
| version | `integer NOT NULL DEFAULT 1` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `CHECK (isfinite(starts_at) AND isfinite(ends_at) AND ends_at > starts_at)`; `CHECK(version > 0)`.

## window_periods

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| window_id | `uuid NOT NULL REFERENCES engineering_windows(id) ON DELETE RESTRICT` |
| kind | `text NOT NULL` |
| starts_at | `timestamptz NOT NULL` |
| ends_at | `timestamptz NOT NULL` |
| period | `tstzrange GENERATED ALWAYS AS (tstzrange(starts_at, ends_at, '[)')) STORED` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `CHECK(kind IN ('permitted_work','service_shutdown'))`; `CHECK (isfinite(starts_at) AND isfinite(ends_at) AND ends_at > starts_at)`.

## sector_availability

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| window_id | `uuid NOT NULL REFERENCES engineering_windows(id) ON DELETE RESTRICT` |
| sector_id | `uuid NOT NULL REFERENCES track_sectors(id) ON DELETE RESTRICT` |
| available | `boolean NOT NULL` |
| starts_at | `timestamptz NOT NULL` |
| ends_at | `timestamptz NOT NULL` |
| period | `tstzrange GENERATED ALWAYS AS (tstzrange(starts_at, ends_at, '[)')) STORED` |
| reason | `text` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `CHECK (isfinite(starts_at) AND isfinite(ends_at) AND ends_at > starts_at)`.

## work_types

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| code | `text NOT NULL UNIQUE` |
| name | `text NOT NULL` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

## request_statuses

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| code | `text NOT NULL UNIQUE` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

## maintenance_requests

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| request_code | `text NOT NULL UNIQUE DEFAULT ('MR-' || lpad(nextval('request_code_seq')::text,6,'0'))` |
| window_id | `uuid NOT NULL REFERENCES engineering_windows(id) ON DELETE RESTRICT` |
| department_id | `uuid NOT NULL REFERENCES departments(id) ON DELETE RESTRICT` |
| work_type_id | `uuid NOT NULL REFERENCES work_types(id) ON DELETE RESTRICT` |
| title | `text NOT NULL CHECK(length(trim(title)) > 0)` |
| description | `text NOT NULL DEFAULT ''` |
| priority | `text NOT NULL DEFAULT 'normal'` |
| status_code | `text NOT NULL REFERENCES request_statuses(code) DEFAULT 'draft'` |
| requested_start | `timestamptz NOT NULL` |
| requested_end | `timestamptz NOT NULL` |
| requested_period | `tstzrange GENERATED ALWAYS AS (tstzrange(requested_start,requested_end,'[)')) STORED` |
| min_duration_minutes | `integer NOT NULL` |
| max_duration_minutes | `integer NOT NULL` |
| earliest_start | `timestamptz NOT NULL` |
| latest_finish | `timestamptz NOT NULL` |
| flexibility | `text NOT NULL DEFAULT 'flexible'` |
| operational_impact | `text` |
| safety_classification | `text NOT NULL DEFAULT 'unreviewed'` |
| created_by | `uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT` |
| submitted_by | `uuid REFERENCES users(id) ON DELETE RESTRICT` |
| submitted_at | `timestamptz` |
| cancelled_at | `timestamptz` |
| cancellation_reason | `text` |
| version | `integer NOT NULL DEFAULT 1` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `CHECK(priority IN ('normal','high','urgent'))`; `CHECK(flexibility IN ('fixed','flexible'))`; `CHECK(isfinite(requested_start) AND isfinite(requested_end) AND requested_end > requested_start)`; `CHECK(isfinite(earliest_start) AND isfinite(latest_finish) AND earliest_start <= requested_start AND requested_end <= latest_finish)`; `CHECK(min_duration_minutes > 0 AND max_duration_minutes >= min_duration_minutes)`; `CHECK(extract(epoch FROM requested_end-requested_start)/60 BETWEEN min_duration_minutes AND max_duration_minutes)`; `CHECK(version > 0)`.

## request_sectors

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| request_id | `uuid NOT NULL REFERENCES maintenance_requests(id) ON DELETE RESTRICT` |
| sector_id | `uuid NOT NULL REFERENCES track_sectors(id) ON DELETE RESTRICT` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `UNIQUE(request_id,sector_id)`.

## request_workzones

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| request_id | `uuid NOT NULL REFERENCES maintenance_requests(id) ON DELETE RESTRICT` |
| workzone_id | `uuid NOT NULL REFERENCES workzones(id) ON DELETE RESTRICT` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `UNIQUE(request_id,workzone_id)`.

## teams

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| department_id | `uuid NOT NULL REFERENCES departments(id) ON DELETE RESTRICT` |
| name | `text NOT NULL` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `UNIQUE(department_id,name)`.

## engineers

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| department_id | `uuid NOT NULL REFERENCES departments(id) ON DELETE RESTRICT` |
| user_id | `uuid REFERENCES users(id) ON DELETE RESTRICT` |
| employee_code | `text NOT NULL UNIQUE` |
| name | `text NOT NULL` |
| active | `boolean NOT NULL DEFAULT true` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

## skills

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| code | `text NOT NULL UNIQUE` |
| name | `text NOT NULL` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

## engineer_skills

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| engineer_id | `uuid NOT NULL REFERENCES engineers(id) ON DELETE RESTRICT` |
| skill_id | `uuid NOT NULL REFERENCES skills(id) ON DELETE RESTRICT` |
| starts_at | `timestamptz NOT NULL` |
| ends_at | `timestamptz NOT NULL` |
| period | `tstzrange GENERATED ALWAYS AS (tstzrange(starts_at, ends_at, '[)')) STORED` |
| certificate_reference | `text NOT NULL` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `CHECK (isfinite(starts_at) AND isfinite(ends_at) AND ends_at > starts_at)`.

## team_memberships

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| team_id | `uuid NOT NULL REFERENCES teams(id) ON DELETE RESTRICT` |
| engineer_id | `uuid NOT NULL REFERENCES engineers(id) ON DELETE RESTRICT` |
| starts_at | `timestamptz NOT NULL` |
| ends_at | `timestamptz NOT NULL` |
| period | `tstzrange GENERATED ALWAYS AS (tstzrange(starts_at, ends_at, '[)')) STORED` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `CHECK (isfinite(starts_at) AND isfinite(ends_at) AND ends_at > starts_at)`.

## shifts

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| department_id | `uuid NOT NULL REFERENCES departments(id) ON DELETE RESTRICT` |
| name | `text NOT NULL` |
| starts_at | `timestamptz NOT NULL` |
| ends_at | `timestamptz NOT NULL` |
| period | `tstzrange GENERATED ALWAYS AS (tstzrange(starts_at, ends_at, '[)')) STORED` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `CHECK (isfinite(starts_at) AND isfinite(ends_at) AND ends_at > starts_at)`.

## engineer_availability

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| engineer_id | `uuid NOT NULL REFERENCES engineers(id) ON DELETE RESTRICT` |
| shift_id | `uuid REFERENCES shifts(id) ON DELETE RESTRICT` |
| available | `boolean NOT NULL` |
| starts_at | `timestamptz NOT NULL` |
| ends_at | `timestamptz NOT NULL` |
| period | `tstzrange GENERATED ALWAYS AS (tstzrange(starts_at, ends_at, '[)')) STORED` |
| reason | `text` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `CHECK (isfinite(starts_at) AND isfinite(ends_at) AND ends_at > starts_at)`.

## team_availability

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| team_id | `uuid NOT NULL REFERENCES teams(id) ON DELETE RESTRICT` |
| shift_id | `uuid REFERENCES shifts(id) ON DELETE RESTRICT` |
| available | `boolean NOT NULL` |
| starts_at | `timestamptz NOT NULL` |
| ends_at | `timestamptz NOT NULL` |
| period | `tstzrange GENERATED ALWAYS AS (tstzrange(starts_at, ends_at, '[)')) STORED` |
| reason | `text` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `CHECK (isfinite(starts_at) AND isfinite(ends_at) AND ends_at > starts_at)`.

## request_teams

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| request_id | `uuid NOT NULL REFERENCES maintenance_requests(id) ON DELETE RESTRICT` |
| team_id | `uuid NOT NULL REFERENCES teams(id) ON DELETE RESTRICT` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `UNIQUE(request_id,team_id)`.

## request_engineers

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| request_id | `uuid NOT NULL REFERENCES maintenance_requests(id) ON DELETE RESTRICT` |
| engineer_id | `uuid NOT NULL REFERENCES engineers(id) ON DELETE RESTRICT` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `UNIQUE(request_id,engineer_id)`.

## request_skills

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| request_id | `uuid NOT NULL REFERENCES maintenance_requests(id) ON DELETE RESTRICT` |
| skill_id | `uuid NOT NULL REFERENCES skills(id) ON DELETE RESTRICT` |
| required_count | `integer NOT NULL DEFAULT 1 CHECK(required_count > 0)` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `UNIQUE(request_id,skill_id)`.

## equipment_types

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| code | `text NOT NULL UNIQUE` |
| name | `text NOT NULL` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

## equipment_assets

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| department_id | `uuid NOT NULL REFERENCES departments(id) ON DELETE RESTRICT` |
| type_id | `uuid NOT NULL REFERENCES equipment_types(id) ON DELETE RESTRICT` |
| asset_code | `text NOT NULL UNIQUE` |
| name | `text NOT NULL` |
| active | `boolean NOT NULL DEFAULT true` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

## equipment_capabilities

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| code | `text NOT NULL UNIQUE` |
| name | `text NOT NULL` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

## asset_capabilities

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| asset_id | `uuid NOT NULL REFERENCES equipment_assets(id) ON DELETE RESTRICT` |
| capability_id | `uuid NOT NULL REFERENCES equipment_capabilities(id) ON DELETE RESTRICT` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `UNIQUE(asset_id,capability_id)`.

## equipment_availability

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| asset_id | `uuid NOT NULL REFERENCES equipment_assets(id) ON DELETE RESTRICT` |
| available | `boolean NOT NULL` |
| starts_at | `timestamptz NOT NULL` |
| ends_at | `timestamptz NOT NULL` |
| period | `tstzrange GENERATED ALWAYS AS (tstzrange(starts_at, ends_at, '[)')) STORED` |
| reason | `text` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `CHECK (isfinite(starts_at) AND isfinite(ends_at) AND ends_at > starts_at)`.

## request_equipment_requirements

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| request_id | `uuid NOT NULL REFERENCES maintenance_requests(id) ON DELETE RESTRICT` |
| type_id | `uuid NOT NULL REFERENCES equipment_types(id) ON DELETE RESTRICT` |
| quantity | `integer NOT NULL DEFAULT 1 CHECK(quantity > 0)` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `UNIQUE(request_id,type_id)`.

## request_equipment_assets

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| request_id | `uuid NOT NULL REFERENCES maintenance_requests(id) ON DELETE RESTRICT` |
| asset_id | `uuid NOT NULL REFERENCES equipment_assets(id) ON DELETE RESTRICT` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `UNIQUE(request_id,asset_id)`.

## request_capabilities

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| request_id | `uuid NOT NULL REFERENCES maintenance_requests(id) ON DELETE RESTRICT` |
| capability_id | `uuid NOT NULL REFERENCES equipment_capabilities(id) ON DELETE RESTRICT` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `UNIQUE(request_id,capability_id)`.

## request_isolations

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| request_id | `uuid NOT NULL REFERENCES maintenance_requests(id) ON DELETE RESTRICT` |
| isolation_zone_id | `uuid NOT NULL REFERENCES isolation_zones(id) ON DELETE RESTRICT` |
| required_state | `text NOT NULL` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `UNIQUE(request_id,isolation_zone_id)`; `CHECK(required_state IN ('isolated','restored'))`.

## compatibility_rules

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| first_work_type_id | `uuid NOT NULL REFERENCES work_types(id) ON DELETE RESTRICT` |
| second_work_type_id | `uuid NOT NULL REFERENCES work_types(id) ON DELETE RESTRICT` |
| compatible | `boolean NOT NULL` |
| minimum_separation_metres | `numeric NOT NULL DEFAULT 0 CHECK(minimum_separation_metres >= 0)` |
| version | `integer NOT NULL DEFAULT 1` |
| rationale | `text NOT NULL` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `UNIQUE(first_work_type_id,second_work_type_id,version)`; `CHECK(first_work_type_id <= second_work_type_id)`.

## rule_definitions

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| code | `text NOT NULL` |
| version | `integer NOT NULL DEFAULT 1` |
| name | `text NOT NULL` |
| category | `text NOT NULL` |
| severity | `text NOT NULL` |
| blocking | `boolean NOT NULL DEFAULT true` |
| enabled | `boolean NOT NULL DEFAULT true` |
| parameters | `jsonb NOT NULL DEFAULT '{}'` |
| authority_reference | `text NOT NULL DEFAULT 'SYNTHETIC - not an operational rule'` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `UNIQUE(code,version)`; `CHECK(severity IN ('information','low','medium','high','critical'))`.

## dependency_types

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| code | `text NOT NULL UNIQUE` |
| name | `text NOT NULL` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

## request_dependencies

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| predecessor_id | `uuid NOT NULL REFERENCES maintenance_requests(id) ON DELETE RESTRICT` |
| successor_id | `uuid NOT NULL REFERENCES maintenance_requests(id) ON DELETE RESTRICT` |
| dependency_type_id | `uuid NOT NULL REFERENCES dependency_types(id) ON DELETE RESTRICT` |
| lag_minutes | `integer NOT NULL DEFAULT 0 CHECK(lag_minutes >= 0)` |
| explanation | `text NOT NULL` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `UNIQUE(predecessor_id,successor_id,dependency_type_id)`; `CHECK(predecessor_id <> successor_id)`.

## travel_times

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| from_sector_id | `uuid NOT NULL REFERENCES track_sectors(id) ON DELETE RESTRICT` |
| to_sector_id | `uuid NOT NULL REFERENCES track_sectors(id) ON DELETE RESTRICT` |
| minutes | `integer NOT NULL CHECK(minutes >= 0)` |
| source | `text NOT NULL` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `UNIQUE(from_sector_id,to_sector_id)`.

## optimisation_objectives

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| code | `text NOT NULL UNIQUE` |
| name | `text NOT NULL` |
| weights | `jsonb NOT NULL DEFAULT '{}'` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

## optimisation_runs

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| window_id | `uuid NOT NULL REFERENCES engineering_windows(id) ON DELETE RESTRICT` |
| objective_id | `uuid NOT NULL REFERENCES optimisation_objectives(id) ON DELETE RESTRICT` |
| requested_by | `uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT` |
| status | `text NOT NULL DEFAULT 'queued'` |
| parameters | `jsonb NOT NULL DEFAULT '{}'` |
| input_snapshot | `jsonb NOT NULL` |
| solver_version | `text` |
| runtime_ms | `integer CHECK(runtime_ms >= 0)` |
| error_message | `text` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `CHECK(status IN ('queued','running','feasible','optimal','infeasible','timed_out','failed'))`.

## scenarios

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| run_id | `uuid NOT NULL REFERENCES optimisation_runs(id) ON DELETE RESTRICT` |
| name | `text NOT NULL` |
| status | `text NOT NULL DEFAULT 'draft'` |
| version | `integer NOT NULL DEFAULT 1` |
| validation_status | `text NOT NULL DEFAULT 'unvalidated'` |
| provenance | `text NOT NULL DEFAULT 'solver'` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `CHECK(status IN ('draft','pending_review','approved','rejected','superseded','withdrawn'))`; `CHECK(validation_status IN ('unvalidated','valid','invalid'))`; `CHECK(version > 0)`.

## scenario_assignments

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| scenario_id | `uuid NOT NULL REFERENCES scenarios(id) ON DELETE RESTRICT` |
| request_id | `uuid NOT NULL REFERENCES maintenance_requests(id) ON DELETE RESTRICT` |
| request_version | `integer NOT NULL CHECK(request_version>0)` |
| original_start | `timestamptz NOT NULL` |
| original_end | `timestamptz NOT NULL` |
| starts_at | `timestamptz NOT NULL` |
| ends_at | `timestamptz NOT NULL` |
| period | `tstzrange GENERATED ALWAYS AS (tstzrange(starts_at, ends_at, '[)')) STORED` |
| reason | `text NOT NULL` |
| feasible | `boolean NOT NULL DEFAULT false` |
| locked | `boolean NOT NULL DEFAULT false` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `UNIQUE(scenario_id,request_id)`; `CHECK(original_end>original_start)`; `CHECK (isfinite(starts_at) AND isfinite(ends_at) AND ends_at > starts_at)`.

## scenario_sectors

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| assignment_id | `uuid NOT NULL REFERENCES scenario_assignments(id) ON DELETE RESTRICT` |
| sector_id | `uuid NOT NULL REFERENCES track_sectors(id) ON DELETE RESTRICT` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `UNIQUE(assignment_id,sector_id)`.

## scenario_teams

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| assignment_id | `uuid NOT NULL REFERENCES scenario_assignments(id) ON DELETE RESTRICT` |
| team_id | `uuid NOT NULL REFERENCES teams(id) ON DELETE RESTRICT` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `UNIQUE(assignment_id,team_id)`.

## scenario_engineers

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| assignment_id | `uuid NOT NULL REFERENCES scenario_assignments(id) ON DELETE RESTRICT` |
| engineer_id | `uuid NOT NULL REFERENCES engineers(id) ON DELETE RESTRICT` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `UNIQUE(assignment_id,engineer_id)`.

## scenario_equipment

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| assignment_id | `uuid NOT NULL REFERENCES scenario_assignments(id) ON DELETE RESTRICT` |
| asset_id | `uuid NOT NULL REFERENCES equipment_assets(id) ON DELETE RESTRICT` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `UNIQUE(assignment_id,asset_id)`.

## possessions

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| scenario_id | `uuid NOT NULL REFERENCES scenarios(id) ON DELETE RESTRICT` |
| code | `text NOT NULL` |
| exclusive | `boolean NOT NULL DEFAULT true` |
| starts_at | `timestamptz NOT NULL` |
| ends_at | `timestamptz NOT NULL` |
| period | `tstzrange GENERATED ALWAYS AS (tstzrange(starts_at, ends_at, '[)')) STORED` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `CHECK (isfinite(starts_at) AND isfinite(ends_at) AND ends_at > starts_at)`; `UNIQUE(scenario_id,code)`.

## possession_sectors

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| possession_id | `uuid NOT NULL REFERENCES possessions(id) ON DELETE RESTRICT` |
| sector_id | `uuid NOT NULL REFERENCES track_sectors(id) ON DELETE RESTRICT` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `UNIQUE(possession_id,sector_id)`.

## possession_assignments

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| possession_id | `uuid NOT NULL REFERENCES possessions(id) ON DELETE RESTRICT` |
| assignment_id | `uuid NOT NULL REFERENCES scenario_assignments(id) ON DELETE RESTRICT` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `UNIQUE(possession_id,assignment_id)`.

## isolation_plans

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| scenario_id | `uuid NOT NULL REFERENCES scenarios(id) ON DELETE RESTRICT` |
| isolation_zone_id | `uuid NOT NULL REFERENCES isolation_zones(id) ON DELETE RESTRICT` |
| starts_at | `timestamptz NOT NULL` |
| ends_at | `timestamptz NOT NULL` |
| period | `tstzrange GENERATED ALWAYS AS (tstzrange(starts_at, ends_at, '[)')) STORED` |
| restored_at | `timestamptz NOT NULL` |
| handback_at | `timestamptz NOT NULL` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `CHECK (isfinite(starts_at) AND isfinite(ends_at) AND ends_at > starts_at)`; `CHECK(restored_at>=ends_at AND handback_at>=restored_at)`.

## scenario_metrics

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| scenario_id | `uuid NOT NULL REFERENCES scenarios(id) ON DELETE RESTRICT` |
| conflicts_resolved | `integer NOT NULL DEFAULT 0 CHECK(conflicts_resolved>=0)` |
| unresolved_conflicts | `integer NOT NULL DEFAULT 0 CHECK(unresolved_conflicts>=0)` |
| requests_moved | `integer NOT NULL DEFAULT 0 CHECK(requests_moved>=0)` |
| total_movement_minutes | `numeric NOT NULL DEFAULT 0 CHECK(total_movement_minutes>=0)` |
| possession_count | `integer NOT NULL DEFAULT 0 CHECK(possession_count>=0)` |
| disruption_score | `numeric CHECK(disruption_score>=0)` |
| resource_utilisation | `numeric CHECK(resource_utilisation BETWEEN 0 AND 1)` |
| unscheduled_requests | `integer NOT NULL DEFAULT 0 CHECK(unscheduled_requests>=0)` |
| solver_status | `text NOT NULL` |
| solver_runtime_ms | `integer CHECK(solver_runtime_ms>=0)` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `UNIQUE(scenario_id)`.

## scoring_policies

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| code | `text NOT NULL` |
| version | `integer NOT NULL` |
| weights | `jsonb NOT NULL` |
| is_validated | `boolean NOT NULL DEFAULT false` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `UNIQUE(code,version)`.

## analysis_runs

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| window_id | `uuid NOT NULL REFERENCES engineering_windows(id) ON DELETE RESTRICT` |
| scenario_id | `uuid REFERENCES scenarios(id) ON DELETE RESTRICT` |
| requested_by | `uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT` |
| scoring_policy_id | `uuid REFERENCES scoring_policies(id) ON DELETE RESTRICT` |
| status | `text NOT NULL DEFAULT 'queued'` |
| input_snapshot | `jsonb NOT NULL` |
| rule_snapshot | `jsonb NOT NULL` |
| completed_at | `timestamptz` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `CHECK(status IN ('queued','running','completed','failed'))`.

## conflicts

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| conflict_code | `text NOT NULL UNIQUE DEFAULT ('CF-' || lpad(nextval('conflict_code_seq')::text,6,'0'))` |
| analysis_run_id | `uuid NOT NULL REFERENCES analysis_runs(id) ON DELETE RESTRICT` |
| rule_id | `uuid NOT NULL REFERENCES rule_definitions(id) ON DELETE RESTRICT` |
| title | `text NOT NULL` |
| explanation | `text NOT NULL` |
| severity | `text NOT NULL` |
| risk_score | `numeric CHECK(risk_score BETWEEN 0 AND 100)` |
| resolution_status | `text NOT NULL DEFAULT 'open'` |
| resolution_notes | `text` |
| detection_method | `text NOT NULL DEFAULT 'automatic'` |
| detected_at | `timestamptz NOT NULL DEFAULT now()` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `CHECK(severity IN ('information','low','medium','high','critical'))`; `CHECK(resolution_status IN ('open','resolved','dismissed'))`; `CHECK(detection_method IN ('automatic','manual','synthetic'))`.

## conflict_requests

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| conflict_id | `uuid NOT NULL REFERENCES conflicts(id) ON DELETE RESTRICT` |
| request_id | `uuid NOT NULL REFERENCES maintenance_requests(id) ON DELETE RESTRICT` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `UNIQUE(conflict_id,request_id)`.

## conflict_teams

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| conflict_id | `uuid NOT NULL REFERENCES conflicts(id) ON DELETE RESTRICT` |
| team_id | `uuid NOT NULL REFERENCES teams(id) ON DELETE RESTRICT` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `UNIQUE(conflict_id,team_id)`.

## conflict_engineers

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| conflict_id | `uuid NOT NULL REFERENCES conflicts(id) ON DELETE RESTRICT` |
| engineer_id | `uuid NOT NULL REFERENCES engineers(id) ON DELETE RESTRICT` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `UNIQUE(conflict_id,engineer_id)`.

## conflict_equipment

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| conflict_id | `uuid NOT NULL REFERENCES conflicts(id) ON DELETE RESTRICT` |
| asset_id | `uuid NOT NULL REFERENCES equipment_assets(id) ON DELETE RESTRICT` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `UNIQUE(conflict_id,asset_id)`.

## conflict_sectors

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| conflict_id | `uuid NOT NULL REFERENCES conflicts(id) ON DELETE RESTRICT` |
| sector_id | `uuid NOT NULL REFERENCES track_sectors(id) ON DELETE RESTRICT` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `UNIQUE(conflict_id,sector_id)`.

## conflict_isolations

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| conflict_id | `uuid NOT NULL REFERENCES conflicts(id) ON DELETE RESTRICT` |
| isolation_zone_id | `uuid NOT NULL REFERENCES isolation_zones(id) ON DELETE RESTRICT` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `UNIQUE(conflict_id,isolation_zone_id)`.

## conflict_score_components

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| conflict_id | `uuid NOT NULL REFERENCES conflicts(id) ON DELETE RESTRICT` |
| component | `text NOT NULL` |
| score | `numeric NOT NULL CHECK(score BETWEEN 0 AND 100)` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `UNIQUE(conflict_id,component)`; `CHECK(component IN ('safety','operational','resource','urgency','passenger'))`.

## request_locks

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| request_id | `uuid NOT NULL REFERENCES maintenance_requests(id) ON DELETE RESTRICT` |
| scenario_id | `uuid REFERENCES scenarios(id) ON DELETE RESTRICT` |
| locked_by | `uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT` |
| scope | `text NOT NULL` |
| reason | `text NOT NULL` |
| locked_values | `jsonb NOT NULL` |
| expires_at | `timestamptz` |
| released_at | `timestamptz` |
| released_by | `uuid REFERENCES users(id) ON DELETE RESTRICT` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `CHECK(scope IN ('request','scenario'))`; `CHECK((scope='request' AND scenario_id IS NULL) OR (scope='scenario' AND scenario_id IS NOT NULL))`; `CHECK(expires_at IS NULL OR expires_at>created_at)`; `CHECK(released_at IS NULL OR released_at>=created_at)`.

## lock_fields

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| lock_id | `uuid NOT NULL REFERENCES request_locks(id) ON DELETE RESTRICT` |
| field | `text NOT NULL` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `UNIQUE(lock_id,field)`; `CHECK(field IN ('timing','team','engineers','equipment','sectors'))`.

## approval_workflows

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| operator_id | `uuid NOT NULL REFERENCES operators(id) ON DELETE RESTRICT` |
| name | `text NOT NULL` |
| version | `integer NOT NULL DEFAULT 1` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `UNIQUE(operator_id,name,version)`.

## approval_stages

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| workflow_id | `uuid NOT NULL REFERENCES approval_workflows(id) ON DELETE RESTRICT` |
| required_role_id | `uuid NOT NULL REFERENCES roles(id) ON DELETE RESTRICT` |
| sequence_no | `integer NOT NULL CHECK(sequence_no>0)` |
| name | `text NOT NULL` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `UNIQUE(workflow_id,sequence_no)`.

## approval_requests

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| scenario_id | `uuid NOT NULL REFERENCES scenarios(id) ON DELETE RESTRICT` |
| workflow_id | `uuid NOT NULL REFERENCES approval_workflows(id) ON DELETE RESTRICT` |
| submitted_by | `uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT` |
| scenario_version | `integer NOT NULL` |
| status | `text NOT NULL DEFAULT 'pending_review'` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `CHECK(status IN ('pending_review','approved','rejected','withdrawn'))`.

## approval_decisions

Append-only history.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| approval_request_id | `uuid NOT NULL REFERENCES approval_requests(id) ON DELETE RESTRICT` |
| stage_id | `uuid NOT NULL REFERENCES approval_stages(id) ON DELETE RESTRICT` |
| approver_id | `uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT` |
| decision | `text NOT NULL` |
| comment | `text NOT NULL` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `UNIQUE(approval_request_id,stage_id)`; `CHECK(decision IN ('approved','rejected'))`.

## schedule_versions

Append-only history.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| window_id | `uuid NOT NULL REFERENCES engineering_windows(id) ON DELETE RESTRICT` |
| scenario_id | `uuid NOT NULL REFERENCES scenarios(id) ON DELETE RESTRICT` |
| approval_request_id | `uuid NOT NULL REFERENCES approval_requests(id) ON DELETE RESTRICT` |
| approved_by | `uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT` |
| version_no | `integer NOT NULL CHECK(version_no>0)` |
| snapshot | `jsonb NOT NULL` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `UNIQUE(window_id,version_no)`; `UNIQUE(approval_request_id)`.

## active_schedules

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| window_id | `uuid NOT NULL REFERENCES engineering_windows(id) ON DELETE RESTRICT` |
| schedule_version_id | `uuid NOT NULL REFERENCES schedule_versions(id) ON DELETE RESTRICT` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `UNIQUE(window_id)`; `UNIQUE(schedule_version_id)`.

## audit_logs

Append-only history.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| actor_id | `uuid REFERENCES users(id) ON DELETE RESTRICT` |
| action | `text NOT NULL` |
| entity_type | `text NOT NULL` |
| entity_id | `uuid NOT NULL` |
| before_state | `jsonb` |
| after_state | `jsonb` |
| correlation_id | `uuid` |
| source | `text NOT NULL` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |

## activity_events

Append-only history.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| actor_id | `uuid REFERENCES users(id) ON DELETE RESTRICT` |
| event_type | `text NOT NULL` |
| message | `text NOT NULL` |
| entity_type | `text` |
| entity_id | `uuid` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |

## event_reads

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| event_id | `uuid NOT NULL REFERENCES activity_events(id) ON DELETE RESTRICT` |
| user_id | `uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT` |
| read_at | `timestamptz NOT NULL DEFAULT now()` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `UNIQUE(event_id,user_id)`.

## copilot_conversations

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| user_id | `uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT` |
| title | `text NOT NULL` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

## copilot_messages

Append-only history.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| conversation_id | `uuid NOT NULL REFERENCES copilot_conversations(id) ON DELETE RESTRICT` |
| role | `text NOT NULL` |
| content | `text NOT NULL` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `CHECK(role IN ('user','assistant','tool'))`.

## copilot_tool_calls

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| message_id | `uuid NOT NULL REFERENCES copilot_messages(id) ON DELETE RESTRICT` |
| actor_id | `uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT` |
| tool_name | `text NOT NULL` |
| arguments | `jsonb NOT NULL` |
| result | `jsonb` |
| status | `text NOT NULL` |
| correlation_id | `uuid NOT NULL` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `CHECK(status IN ('pending','succeeded','failed','denied'))`.

## copilot_request_refs

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| message_id | `uuid NOT NULL REFERENCES copilot_messages(id) ON DELETE RESTRICT` |
| request_id | `uuid NOT NULL REFERENCES maintenance_requests(id) ON DELETE RESTRICT` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `UNIQUE(message_id,request_id)`.

## copilot_conflict_refs

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| message_id | `uuid NOT NULL REFERENCES copilot_messages(id) ON DELETE RESTRICT` |
| conflict_id | `uuid NOT NULL REFERENCES conflicts(id) ON DELETE RESTRICT` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `UNIQUE(message_id,conflict_id)`.

## Scenario A pure result and saved API extension

`OptimiseInput` bounds wall/deterministic budgets, seed and physical-night count, with
optional locked/baseline placements. `OptimiseResult` retains solver/optimality status,
objective components, organiser CSV text, explicit `physical_nights` placement records,
rich validation report, policy/settings, stage bounds and completion changes. Physical
night scope is network/week; access index scope is contract/type/week; possession group
scope is location/week. `SavedOptimiseInput` adds only API baseline_run_id/idempotency_key;
`SavedOptimiseResult` keeps all original top-level fields and adds run metadata. Pure
solver/CLI contracts remain database-free; migration 0007 stores their terminal snapshots.
See PS1_OPTIMISATION_PERSISTENCE.md.

## copilot_scenario_refs

Mutable operational/reference data.

| Column | SQL definition |
|---|---|
| id | `uuid PRIMARY KEY DEFAULT gen_random_uuid()` |
| message_id | `uuid NOT NULL REFERENCES copilot_messages(id) ON DELETE RESTRICT` |
| scenario_id | `uuid NOT NULL REFERENCES scenarios(id) ON DELETE RESTRICT` |
| created_at | `timestamptz NOT NULL DEFAULT now()` |
| updated_at | `timestamptz NOT NULL DEFAULT now()` |

Constraints: `UNIQUE(message_id,scenario_id)`.
