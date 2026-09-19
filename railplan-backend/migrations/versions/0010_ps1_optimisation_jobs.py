"""Durable asynchronous PS1 optimisation job state."""
from pathlib import Path
from alembic import op

revision='0010'
down_revision='0009'
branch_labels=None
depends_on=None

def upgrade():
    op.get_bind().exec_driver_sql((Path(__file__).resolve().parents[2]/'sql/013_ps1_optimisation_jobs.sql').read_text(),execution_options={'no_parameters':True})

def downgrade():
    raise RuntimeError('Archive optimisation jobs before removing their history')
