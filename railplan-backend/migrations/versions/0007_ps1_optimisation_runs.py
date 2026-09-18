"""Sealed, operator-scoped terminal PS1 optimiser results."""
from pathlib import Path
from alembic import op
revision='0007'
down_revision='0006'
branch_labels=None
depends_on=None

def upgrade():
    op.get_bind().exec_driver_sql((Path(__file__).resolve().parents[2]/'sql/010_ps1_optimisation_runs.sql').read_text(),execution_options={'no_parameters':True})

def downgrade():
    raise RuntimeError('Archive sealed PS1 optimisation evidence before removing its immutable history')
