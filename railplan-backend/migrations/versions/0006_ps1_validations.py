"""Immutable provisional PS1 validation runs and evidence."""
from pathlib import Path
from alembic import op
revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None

def upgrade():
    op.get_bind().exec_driver_sql((Path(__file__).resolve().parents[2]/'sql/009_ps1_validations.sql').read_text(),
                                execution_options={'no_parameters':True})

def downgrade():
    raise RuntimeError('Archive validation evidence before removing its immutable history')
