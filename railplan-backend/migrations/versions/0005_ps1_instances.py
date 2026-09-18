"""PS1 weekly instance imports, separate from nightly demo schedules."""
from pathlib import Path
from alembic import op
revision="0005"
down_revision="0004"
branch_labels=None
depends_on=None

def upgrade():
    op.get_bind().exec_driver_sql((Path(__file__).resolve().parents[2]/"sql/008_ps1_instances.sql").read_text(),
                                execution_options={"no_parameters":True})

def downgrade():
    raise RuntimeError("Archive imported instances before removing their history")
