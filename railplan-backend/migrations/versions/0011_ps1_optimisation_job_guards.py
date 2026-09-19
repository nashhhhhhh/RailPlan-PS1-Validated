"""PS1 optimisation job lifecycle guards and audit triggers."""
from pathlib import Path
from alembic import op

revision='0011'
down_revision='0010'
branch_labels=None
depends_on=None

def upgrade():
    op.get_bind().exec_driver_sql((Path(__file__).resolve().parents[2]/'sql/014_ps1_optimisation_job_guards.sql').read_text(),execution_options={'no_parameters':True})

def downgrade():
    raise RuntimeError('Archive optimisation job audit history before removing lifecycle guards')
