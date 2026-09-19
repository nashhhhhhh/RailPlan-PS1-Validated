-- Lifecycle validation and audit evidence for mutable job-control rows.
CREATE FUNCTION railplan.ps1_job_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='INSERT' THEN
  IF NOT EXISTS(SELECT 1 FROM railplan.users u JOIN railplan.departments d ON d.id=u.department_id
                WHERE u.id=NEW.created_by AND d.operator_id=NEW.operator_id) THEN
   RAISE EXCEPTION 'Optimisation job creator must belong to the instance operator';
  END IF;
  IF NEW.status NOT IN ('QUEUED','SUCCEEDED') THEN RAISE EXCEPTION 'Job must start queued or as an idempotent completed replay'; END IF;
  RETURN NEW;
 END IF;
 IF (NEW.instance_id,NEW.operator_id,NEW.created_by,NEW.scenario,NEW.idempotency_key,NEW.input_fingerprint,NEW.request_snapshot)
    IS DISTINCT FROM
    (OLD.instance_id,OLD.operator_id,OLD.created_by,OLD.scenario,OLD.idempotency_key,OLD.input_fingerprint,OLD.request_snapshot) THEN
  RAISE EXCEPTION 'Optimisation job identity and input are immutable';
 END IF;
 IF NEW.progress<OLD.progress THEN RAISE EXCEPTION 'Optimisation job progress cannot decrease'; END IF;
 IF OLD.status IN ('SUCCEEDED','FAILED','CANCELLED') THEN RAISE EXCEPTION 'Terminal optimisation job is immutable'; END IF;
 IF NOT CASE OLD.status
   WHEN 'QUEUED' THEN NEW.status IN ('RUNNING','CANCELLATION_REQUESTED','FAILED','CANCELLED')
   WHEN 'RUNNING' THEN NEW.status IN ('RUNNING','CANCELLATION_REQUESTED','SUCCEEDED','FAILED','CANCELLED')
   WHEN 'CANCELLATION_REQUESTED' THEN NEW.status IN ('CANCELLATION_REQUESTED','SUCCEEDED','FAILED','CANCELLED')
   ELSE false END THEN
  RAISE EXCEPTION 'Invalid optimisation job transition % to %',OLD.status,NEW.status;
 END IF;
 NEW.updated_at=clock_timestamp();
 IF NEW.status='RUNNING' AND NEW.started_at IS NULL THEN NEW.started_at=NEW.updated_at; END IF;
 IF NEW.status IN ('SUCCEEDED','FAILED','CANCELLED') AND NEW.completed_at IS NULL THEN NEW.completed_at=NEW.updated_at; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER lifecycle_guard BEFORE INSERT OR UPDATE ON railplan.ps1_optimisation_jobs
 FOR EACH ROW EXECUTE FUNCTION railplan.ps1_job_guard();

CREATE FUNCTION railplan.ps1_job_audit() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE doc jsonb;
BEGIN
 doc=to_jsonb(NEW);
 INSERT INTO railplan.audit_logs(actor_id,action,entity_type,entity_id,before_state,after_state,correlation_id,source)
 VALUES(NULLIF(current_setting('railplan.actor_id',true),'')::uuid,TG_OP,'ps1_optimisation_jobs',NEW.id,
   CASE WHEN TG_OP='UPDATE' THEN to_jsonb(OLD) ELSE NULL END,doc,
   NULLIF(current_setting('railplan.correlation_id',true),'')::uuid,
   COALESCE(NULLIF(current_setting('railplan.source',true),''),'worker'));
 RETURN NEW;
END $$;
CREATE TRIGGER audit_change AFTER INSERT OR UPDATE ON railplan.ps1_optimisation_jobs
 FOR EACH ROW EXECUTE FUNCTION railplan.ps1_job_audit();
CREATE TRIGGER immutable_delete BEFORE DELETE ON railplan.ps1_optimisation_jobs
 FOR EACH ROW EXECUTE FUNCTION railplan.deny_mutation();
CREATE TRIGGER immutable_truncate BEFORE TRUNCATE ON railplan.ps1_optimisation_jobs
 FOR EACH STATEMENT EXECUTE FUNCTION railplan.deny_mutation();
