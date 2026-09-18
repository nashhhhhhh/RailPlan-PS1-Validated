"""Add read indexes and invalidate draft validations on request edits."""
from alembic import op
revision="0002"
down_revision="0001"
branch_labels=None
depends_on=None

def upgrade():
    op.get_bind().exec_driver_sql("""
    CREATE INDEX ix_assignments_scenario_start ON railplan.scenario_assignments(scenario_id,starts_at,id);
    CREATE INDEX ix_requests_window_start ON railplan.maintenance_requests(window_id,requested_start,id);
    CREATE INDEX ix_analysis_window_created ON railplan.analysis_runs(window_id,created_at DESC,id);
    CREATE FUNCTION railplan.invalidate_draft_scenarios() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      UPDATE railplan.scenarios SET validation_status='unvalidated'
      WHERE status='draft' AND id IN (SELECT scenario_id FROM railplan.scenario_assignments WHERE request_id=NEW.id);
      RETURN NEW;
    END $$;
    CREATE TRIGGER invalidate_drafts AFTER UPDATE ON railplan.maintenance_requests
      FOR EACH ROW EXECUTE FUNCTION railplan.invalidate_draft_scenarios();
    REVOKE EXECUTE ON FUNCTION railplan.invalidate_draft_scenarios() FROM PUBLIC;
    """,execution_options={"no_parameters":True})

def downgrade():
    op.get_bind().exec_driver_sql("""
    DROP TRIGGER invalidate_drafts ON railplan.maintenance_requests;
    DROP FUNCTION railplan.invalidate_draft_scenarios();
    DROP INDEX railplan.ix_analysis_window_created;
    DROP INDEX railplan.ix_requests_window_start;
    DROP INDEX railplan.ix_assignments_scenario_start;
    """,execution_options={"no_parameters":True})
