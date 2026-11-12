import os
import sys
from pathlib import Path

import pytest_asyncio
from dotenv import load_dotenv
from sqlalchemy import URL
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine


ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"

# Добавляем backend в пути поиска Python.
# Благодаря этому можно импортировать модели через app.models.
sys.path.insert(0, str(BACKEND_DIR))

# Загружаем переменные окружения из корневого .env.
load_dotenv(ROOT_DIR / ".env")


def get_test_database_url():
    return URL.create(
        drivername="postgresql+asyncpg",
        username=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        host="127.0.0.1",
        port=5433,
        database="legal_assistant_test",
    )


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine(
        get_test_database_url(),
        echo=False,
    )

    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()

            session = AsyncSession(
                bind=connection,
                expire_on_commit=False,
                join_transaction_mode="create_savepoint",
            )

            try:
                yield session
            finally:
                await session.close()
                await transaction.rollback()

    finally:
        await engine.dispose()