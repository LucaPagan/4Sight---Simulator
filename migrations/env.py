from alembic import context
from sqlalchemy import create_engine

from audience_simulator.config import settings
from audience_simulator.repository import metadata

cfg = settings()
if context.is_offline_mode():
    context.configure(url=cfg.database_url, target_metadata=metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    with create_engine(cfg.database_url).connect() as connection:
        context.configure(connection=connection, target_metadata=metadata)
        with context.begin_transaction():
            context.run_migrations()
