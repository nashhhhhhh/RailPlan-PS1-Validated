"""Versioned deterministic conflict scores and immutable evidence history."""
from pathlib import Path
from alembic import op
revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

def upgrade():
    op.get_bind().exec_driver_sql(
        (Path(__file__).resolve().parents[2]/"sql/005_scoring.sql").read_text(),
        execution_options={"no_parameters": True})

def downgrade():
    raise RuntimeError("Scoring evidence history requires an explicit archival migration")
