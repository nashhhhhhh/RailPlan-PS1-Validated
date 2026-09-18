"""Append-only completed analyses and snapshot-backed coordination queue."""
from pathlib import Path
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    path = Path(__file__).resolve().parents[2] / "sql" / "006_analysis_history.sql"
    op.get_bind().exec_driver_sql(path.read_text(), execution_options={"no_parameters": True})


def downgrade():
    raise RuntimeError("Removing analysis history protection requires a reviewed recovery procedure.")
