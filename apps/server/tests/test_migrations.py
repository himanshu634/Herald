"""Tests for the migrations, the adoption of pre-migration databases and the startup check."""

import pytest
from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable
from sqlmodel import Session, SQLModel, create_engine, select

from herald_server.migrate import (
    SchemaMismatch,
    alembic_config,
    current_revision,
    head_revision,
    schema_differences,
    upgrade,
)
from herald_server.models import Workspace
from herald_server.services import build_services


@pytest.fixture
def db_url(tmp_path) -> str:
    return f"sqlite:///{tmp_path / 'empty.db'}"


def _differences(url: str) -> list[str]:
    engine = create_engine(url)
    with engine.connect() as connection:
        differences = schema_differences(connection)
    engine.dispose()
    return differences


def _revision(url: str) -> str | None:
    engine = create_engine(url)
    with engine.connect() as connection:
        revision = current_revision(connection)
    engine.dispose()
    return revision


def test_migrations_build_the_schema_the_models_describe(db_url):
    # A model change without a migration fails here. `make migration` writes the missing one.
    upgrade(db_url)

    assert _differences(db_url) == []
    assert _revision(db_url) == head_revision()


def test_downgrade_to_nothing_and_back(db_url):
    upgrade(db_url)
    command.downgrade(alembic_config(db_url), "base")

    engine = create_engine(db_url)
    assert inspect(engine).get_table_names() == ["alembic_version"]
    engine.dispose()

    upgrade(db_url)
    assert _differences(db_url) == []


def test_there_is_one_head():
    # Two heads: two branches each added a migration. Run `alembic merge heads` and commit it.
    assert len(ScriptDirectory.from_config(alembic_config("")).get_heads()) == 1


def test_a_database_made_before_migrations_is_adopted_with_its_data(db_url):
    engine = create_engine(db_url)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Workspace(name="Shop", config={}))
        session.commit()
    engine.dispose()

    upgrade(db_url)

    assert _revision(db_url) == head_revision()
    engine = create_engine(db_url)
    with Session(engine) as session:
        assert session.exec(select(Workspace.name)).all() == ["Shop"]
    engine.dispose()


def test_an_older_database_is_refused_and_left_alone(db_url):
    # A workspace table from before the demo column. Stamping it would leave the column out
    # for good, so adoption refuses and says what differs.
    engine = create_engine(db_url)
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE workspace (id CHAR(32) PRIMARY KEY, name VARCHAR, config JSON,"
                " setup_done BOOLEAN, created_at DATETIME)"
            )
        )
    engine.dispose()

    with pytest.raises(SchemaMismatch, match=r"add_column workspace\.demo"):
        upgrade(db_url)
    assert _revision(db_url) is None


def test_startup_refuses_a_database_with_no_schema_version(settings, db_url):
    with pytest.raises(RuntimeError, match="no schema version. Run `make migrate`"):
        build_services(settings.model_copy(update={"database_url": db_url}))


def test_startup_refuses_a_database_on_another_revision(settings):
    engine = create_engine(settings.database_url)
    with engine.begin() as conn:
        conn.execute(text("UPDATE alembic_version SET version_num = 'abc123'"))
    engine.dispose()

    with pytest.raises(RuntimeError, match="at revision abc123, this code needs"):
        build_services(settings)


def test_constraint_names_are_the_ones_postgres_gave_older_databases():
    # Databases made by create_all before migrations got these names from Postgres. If the
    # models named them differently, adoption would refuse every such database.
    ddl = "\n".join(
        str(CreateTable(table).compile(dialect=postgresql.dialect()))
        for table in SQLModel.metadata.sorted_tables
    )
    for name in (
        "workspace_pkey",
        "mailbox_workspace_id_fkey",
        "mailbox_workspace_id_provider_email_address_key",
        "email_mailbox_id_provider_message_id_key",
        "reply_workspace_id_client_key_key",
        "reply_email_id_fkey",
    ):
        assert f"CONSTRAINT {name} " in ddl
