-- Durable operator-scoped job control for persisted PS1 optimisation.
CREATE TABLE railplan.ps1_optimisation_jobs (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 instance_id uuid NOT NULL,
 operator_id uuid NOT NULL REFERENCES railplan.operators(id) ON DELETE RESTRICT,
 created_by uuid NOT NULL REFERENCES railplan.users(id) ON DELETE RESTRICT,
 scenario text NOT NULL CHECK(scenario IN ('A','B','C')),
 status text NOT NULL CHECK(status IN ('QUEUED','RUNNING','CANCELLATION_REQUESTED','SUCCEEDED','FAILED','CANCELLED')),
 progress smallint NOT NULL DEFAULT 0 CHECK(progress BETWEEN 0 AND 100),
 stage text NOT NULL DEFAULT 'queued' CHECK(length(stage) BETWEEN 1 AND 120),
 idempotency_key text CHECK(idempotency_key IS NULL OR (length(idempotency_key) BETWEEN 1 AND 128 AND idempotency_key !~ '[[:space:]]')),
 input_fingerprint text NOT NULL CHECK(length(input_fingerprint)=64),
 request_snapshot jsonb NOT NULL,
 cancel_requested boolean NOT NULL DEFAULT false,
 run_id uuid,
 diagnostic jsonb,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 started_at timestamptz,
 completed_at timestamptz,
 updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(instance_id,operator_id) REFERENCES railplan.ps1_instances(id,operator_id) ON DELETE RESTRICT,
 FOREIGN KEY(run_id,instance_id,operator_id) REFERENCES railplan.ps1_optimisation_runs(id,instance_id,operator_id) ON DELETE RESTRICT,
 CHECK(started_at IS NULL OR started_at>=created_at),
 CHECK(completed_at IS NULL OR (started_at IS NOT NULL AND completed_at>=started_at)),
 CHECK(status<>'SUCCEEDED' OR (progress=100 AND run_id IS NOT NULL AND completed_at IS NOT NULL)),
 CHECK(status NOT IN ('FAILED','CANCELLED') OR completed_at IS NOT NULL)
);
CREATE UNIQUE INDEX ps1_optimisation_job_key ON railplan.ps1_optimisation_jobs(operator_id,instance_id,idempotency_key)
 WHERE idempotency_key IS NOT NULL;
CREATE INDEX ps1_optimisation_job_history ON railplan.ps1_optimisation_jobs(operator_id,instance_id,created_at DESC,id DESC);
CREATE INDEX ps1_optimisation_job_work ON railplan.ps1_optimisation_jobs(status,created_at) WHERE status IN ('QUEUED','RUNNING','CANCELLATION_REQUESTED');
