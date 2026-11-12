
import asyncio
import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import pool
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import create_async_engine

# Пути проекта
BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = Path(__file__).resolve().parents[2]

# Добавляем backend в пути поиска Python
sys.path.insert(0, str(BACKEND_DIR))

# Загружаем переменные из корневого .env
load_dotenv(ROOT_DIR / ".env")

# Импортируем Base и модели
from app.base import Base
from app import models


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Метаданные всех ORM-моделей
target_metadata = Base.metadata


def get_database_url():
    database_url = os.getenv("ALEMBIC_DATABASE_URL")

    if database_url:
        return database_url

    return URL.create(
        drivername="postgresql+asyncpg",
        username=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        host=os.getenv("ALEMBIC_DB_HOST", "127.0.0.1"),
        port=int(os.getenv("ALEMBIC_DB_PORT", "5433")),
        database=os.environ["POSTGRES_DB"],
    )


def run_migrations_offline() -> None:
    url = get_database_url()

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = create_async_engine(
        get_database_url(),
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
