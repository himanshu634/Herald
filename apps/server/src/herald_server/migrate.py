"""Database migrations: bring a database to the latest schema, and check it is there.

`python -m herald_server.migrate` (`make migrate`) upgrades the database. The API and the
worker never change the schema: `check_at_head` stops them at startup until it is done.
Write new migrations with the Alembic CLI from apps/server (see docs/architecture.md).
"""

import logging
import sys
from typing import Any

# Registers its comparator on import, for every migration context in this process. Without
# it, autogenerate and adoption never notice an enum value added to or removed from a model.
import alembic_postgresql_enum  # noqa: F401
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, Engine, inspect
from sqlmodel import SQLModel, create_engine

from herald_server import models  # noqa: F401  puts the tables on SQLModel.metadata
from herald_server.settings import get_settings

log = logging.getLogger(__name__)


class SchemaMismatch(RuntimeError):
    """A database made before migrations does not match the models, so it cannot be adopted."""


def alembic_config(database_url: str) -> Config:
    # Built in code because the production image has no alembic.ini, only the package. The
    # URL goes in attributes, not the ini options: those are interpolated, so a % in a
    # password would break them.
    config = Config()
    config.set_main_option("script_location", "herald_server:migrations")
    config.attributes["database_url"] = database_url
    return config


def context_options(dialect_name: str) -> dict[str, Any]:
    """Options for every migration context, so env.py and adoption compare the same way."""
    # SQLite cannot alter a column or a constraint in place. Batch mode copies the table to a
    # new one instead, so the same migration runs on lite mode and on Postgres.
    return {"target_metadata": SQLModel.metadata, "render_as_batch": dialect_name == "sqlite"}


def head_revision() -> str:
    # Raises when there are two heads: two branches each added a migration. Startup must stop
    # then, since no single revision is "latest". `alembic merge heads` fixes it.
    script = ScriptDirectory.from_config(alembic_config(""))
    head = script.get_current_head()
    assert head is not None, "no migrations in herald_server/migrations/versions"
    return head


def current_revision(connection: Connection) -> str | None:
    return MigrationContext.configure(connection).get_current_revision()


def check_at_head(engine: Engine) -> None:
    """Fail startup when the database is not at the revision this code was written for."""
    head = head_revision()
    with engine.connect() as connection:
        current = current_revision(connection)
    if current is None:
        raise RuntimeError(
            "Database has no schema version. Run `make migrate` "
            "(python -m herald_server.migrate) before starting Herald."
        )
    if current != head:
        raise RuntimeError(
            f"Database is at revision {current}, this code needs {head}. Run `make migrate` "
            "(python -m herald_server.migrate) before starting Herald."
        )


def schema_differences(connection: Connection) -> list[str]:
    """What separates the live database from the models, one line per difference."""
    context = MigrationContext.configure(connection, opts=context_options(connection.dialect.name))
    return [_describe(diff) for diff in compare_metadata(context, SQLModel.metadata)]


def _describe(diff: Any) -> str:
    # compare_metadata gives tuples like ("add_column", schema, "workspace", Column), and a
    # list of such tuples for several changes to one column.
    if isinstance(diff, list):
        return "; ".join(_describe(d) for d in diff)
    op, *rest = diff
    if op == "change_enum_variants":  # From alembic_postgresql_enum: (op, new, old, columns).
        return f"{op} {rest[2][0].table_name}.{rest[2][0].column_name}"
    names = [p if isinstance(p, str) else getattr(p, "name", None) for p in rest]
    return f"{op} {'.'.join(n for n in names[:3] if n)}"


def _adopt(engine: Engine, config: Config) -> None:
    """Stamp a database made by create_all, before migrations, as being at the head.

    Its tables already exist, so running the baseline on it would fail. Stamping marks it as
    migrated without touching it. That is safe only when it matches the models exactly: a
    missing column or index would never be added afterwards. So any difference refuses.
    Once later migrations exist, the models are ahead of every such database, and they all
    get refused. That is the intent: adoption is for databases made before this change.
    """
    with engine.connect() as connection:
        if current_revision(connection) is not None:
            return
        ours = set(SQLModel.metadata.tables)
        if not ours & set(inspect(connection).get_table_names()):
            return  # Empty database: the baseline creates everything.
        differences = schema_differences(connection)
    if differences:
        raise SchemaMismatch(
            "This database was made before migrations and does not match the models, so it "
            f"cannot be adopted. Differences: {', '.join(differences)}. Reset it: delete "
            "apps/server/herald-dev.db (lite mode), or run docker compose -f "
            "infra/docker-compose.yml down -v (this deletes its data), then migrate again."
        )
    command.stamp(config, "head")
    log.info("Adopted a database made before migrations as revision %s", head_revision())


def upgrade(database_url: str) -> None:
    """Bring the database to the latest revision, adopting a pre-migration database first."""
    config = alembic_config(database_url)
    engine = create_engine(database_url)
    try:
        _adopt(engine, config)
    finally:
        engine.dispose()
    command.upgrade(config, "head")


def main() -> None:
    # Its own process, so a root handler is fine. INFO only for the "Running upgrade" lines and
    # this module: autogenerate logs every difference at INFO, and the refusal already lists them.
    logging.basicConfig(level=logging.WARNING, format="%(levelname)-7s %(name)s: %(message)s")
    for name in ("alembic.runtime.migration", __name__):
        logging.getLogger(name).setLevel(logging.INFO)
    try:
        upgrade(get_settings().database_url)
    except SchemaMismatch as error:
        # A message the person can act on, without a traceback. Exits 1, so a deploy stops.
        sys.exit(str(error))


if __name__ == "__main__":
    main()
