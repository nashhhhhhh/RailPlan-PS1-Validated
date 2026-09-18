"""Permit immutable Scenario B optimisation evidence and ECLO decisions."""
from pathlib import Path
from alembic import op

revision='0008'
down_revision='0007'
branch_labels=None
depends_on=None

def upgrade():
    op.get_bind().exec_driver_sql((Path(__file__).resolve().parents[2]/'sql/011_ps1_scenario_b.sql').read_text(),execution_options={'no_parameters':True})

def downgrade():
    raise RuntimeError('Archive sealed Scenario B optimisation evidence before removing support')
