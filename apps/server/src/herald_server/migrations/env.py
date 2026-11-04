"""Alembic environment for herald_server. Run migrations with `make migrate`, not by hand."""

from alembic import context
from sqlalchemy import create_engine, pool

# Also registers alembic_postgresql_enum, so autogenerate compares enum values.
from herald_server.migrate import context_options
from herald_server.settings import get_settings

# Set by herald_server.migrate. Empty when the Alembic CLI runs this, so read the settings.
database_url = context.config.attributes.get("database_url") or get_settings().database_url


def run_offline() -> None:
    # `alembic upgrade --sql`: print the SQL instead of running it.
    dialect = database_url.split(":", 1)[0].split("+", 1)[0]
    context.configure(url=database_url, literal_binds=True, **context_options(dialect))
    with context.begin_transaction():
        context.run_migrations()


def run_online() -> None:
    engine = create_engine(database_url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, **context_options(connection.dialect.name))
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_offline()
else:
    run_online()
