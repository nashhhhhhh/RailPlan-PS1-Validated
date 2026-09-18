"""Initial SQL-authoritative schema. SQL files are versioned migration assets."""
from pathlib import Path
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    root = Path(__file__).resolve().parents[2]
    for name in ("001_schema.sql", "002_guards.sql", "003_views.sql"):
        # psycopg supports multiple statements without bound parameters.
        op.get_bind().exec_driver_sql((root / "sql" / name).read_text(),
                                     execution_options={"no_parameters": True})

def downgrade():
    # Deliberately require an explicit recovery procedure, not accidental history loss.
    raise RuntimeError("Initial schema downgrade is destructive. Restore a tested backup instead.")
