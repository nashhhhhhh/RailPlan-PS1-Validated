import os
from alembic import context
from sqlalchemy import create_engine
from app.models import Base
from app import ps1_models
from app import ps1_optimisation_models
from app import scoring_models

config = context.config
target_metadata = Base.metadata
url = os.environ["DATABASE_URL"]
if context.is_offline_mode():
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    with create_engine(url).connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
