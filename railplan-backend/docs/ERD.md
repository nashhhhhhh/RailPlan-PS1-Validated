# RailPlan domain ER diagrams

Scenario B reuses the sealed `ps1_optimisation_runs` parent and its access, occupancy, contract-result, and idempotency-key children. `scenario` discriminates A/B; `ps1_optimisation_accesses.eclo` retains `0/1`. Workload, excess, stage, policy, and validation structures remain immutable JSON snapshots on the parent.

These are relationship-level diagrams. Full columns and subsidiary junctions are in DATA_DICTIONARY.md.

## Network and requested intent

```mermaid
erDiagram
    operators ||--o{ networks : owns
    networks ||--o{ lines : contains
    networks ||--o{ stations : contains
    lines ||--o{ line_stations : serves
    stations ||--o{ line_stations : has_codes
    lines ||--o{ track_sectors : contains
    track_sectors ||--o{ tracks : contains
    tracks ||--o{ track_segments : contains
    lines ||--o{ engineering_windows : permits
    engineering_windows ||--o{ maintenance_requests : contains
    maintenance_requests ||--o{ request_sectors : occupies
    track_sectors ||--o{ request_sectors : requested
    maintenance_requests ||--o{ request_workzones : locates
    workzones ||--o{ request_workzones : requested
```

## Resource and conflict evidence

```mermaid
erDiagram
    maintenance_requests ||--o{ request_teams : requests
    teams ||--o{ request_teams : assigned
    teams ||--o{ team_memberships : contains
    engineers ||--o{ team_memberships : joins
    engineers ||--o{ engineer_skills : certified
    skills ||--o{ engineer_skills : qualifies
    maintenance_requests ||--o{ request_equipment_requirements : needs
    equipment_types ||--o{ request_equipment_requirements : specifies
    equipment_types ||--o{ equipment_assets : classifies
    analysis_runs ||--o{ conflicts : produces
    rule_definitions ||--o{ conflicts : explains
    conflicts ||--o{ conflict_requests : involves
    maintenance_requests ||--o{ conflict_requests : affected
```

## Alternatives and approved history

```mermaid
erDiagram
    optimisation_runs ||--o{ scenarios : produces
    scenarios ||--o{ scenario_assignments : proposes
    maintenance_requests ||--o{ scenario_assignments : snapshots
    scenario_assignments ||--o{ scenario_engineers : allocates
    engineers ||--o{ scenario_engineers : assigned
    scenarios ||--o{ possessions : groups
    possessions ||--o{ possession_assignments : contains
    scenario_assignments ||--o{ possession_assignments : shares
    scenarios ||--o{ approval_requests : submitted
    approval_workflows ||--o{ approval_stages : defines
    approval_requests ||--o{ approval_decisions : records
    approval_stages ||--o{ approval_decisions : requires
    approval_requests ||--o| schedule_versions : authorizes
    engineering_windows ||--o{ schedule_versions : versions
    schedule_versions ||--o| active_schedules : selected
```

## Relationship notes

Scenario A optimisation reads an operator-scoped immutable `ps1_instances.dataset` and
saves a terminal rich result in dedicated migration-0007 tables. Physical mappings are
not sent through CSV-only validation history. All child rows share operator/instance FKs.

```mermaid
erDiagram
    ps1_instances ||--o{ ps1_optimisation_runs : owns
    ps1_optimisation_runs ||--o{ ps1_optimisation_accesses : contains
    ps1_optimisation_runs ||--o{ ps1_optimisation_occupancies : contains
    ps1_optimisation_runs ||--o{ ps1_optimisation_contract_results : completes
    ps1_optimisation_runs ||--o{ ps1_optimisation_keys : identifies
```

An optional run-to-baseline FK is constrained to the same operator and instance.
Accepted occupancy rows also reference their activity/week access. Creation-transaction
and manifest guards plus deferred checks seal the parent and all child content at commit.
See PS1_OPTIMISATION_PERSISTENCE.md for the full transaction and audit design.

### PS1 immutable history (migration 0006)

```mermaid
erDiagram
    operators ||--o{ ps1_instances : scopes
    ps1_instances ||--o{ ps1_validation_runs : validates
    users ||--o{ ps1_validation_runs : creates
    ps1_validation_runs ||--o{ ps1_validation_violations : records
    ps1_validation_runs ||--o{ ps1_validation_keys : deduplicates
```

Composite parent/operator foreign keys prevent cross-operator child records. All three
validation tables are append-only with audited inserts. PS1 is not linked to legacy
nightly requests or severity scores.

- A request may need many sectors/resources and may have many proposed assignments, one per scenario.
- A conflict belongs to one analysis run but may involve any number of requests/resources.
- An analysis run optionally targets a scenario; NULL means original requested timings.
- Many compatible jobs may share one possession. The possession link checks scenario identity and containment.
- Request locks are independently owned/time-stamped records with relational locked-field definitions.
- Approval decision history and schedule snapshots are append-only. An active pointer is distinct from historical versions.
- Dependencies use predecessor/successor FK pairs and type-specific lag. Cycles require future validator checks.
