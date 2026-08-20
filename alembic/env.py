import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

import app.database.tables
from app.database.base import Base
from app.database.settings import get_database_settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

def run_migrations_offline() -> None:
    settings = get_database_settings()

    context.configure(
        url=settings.async_database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={
            "paramstyle": "named",
        },
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()

def run_migrations_with_connection(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()

async def run_migrations_online_async() -> None:
    settings = get_database_settings()

    connectable = create_async_engine(
        settings.async_database_url,
        poolclass=pool.NullPool,
        connect_args={
            "timeout": 10,
            "server_settings": {
                "application_name": "stock-master-bot-alembic",
            },
        },
    )

    try:
        async with connectable.connect() as connection:
            await connection.run_sync(
                run_migrations_with_connection
            )
    finally:
        await connectable.dispose()

def run_migrations_online() -> None:
    asyncio.run(run_migrations_online_async())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()