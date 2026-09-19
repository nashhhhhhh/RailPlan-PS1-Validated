"""Permit immutable Scenario C optimisation evidence."""
from pathlib import Path
from alembic import op

revision='0009'
down_revision='0008'
branch_labels=None
depends_on=None

def upgrade():
    op.get_bind().exec_driver_sql((Path(__file__).resolve().parents[2]/'sql/012_ps1_scenario_c.sql').read_text(),execution_options={'no_parameters':True})

def downgrade():
    raise RuntimeError('Archive sealed Scenario C optimisation evidence before removing support')
