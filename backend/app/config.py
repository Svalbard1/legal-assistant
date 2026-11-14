import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.engine import URL


BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")


class Settings:
    def __init__(self):
        self.POSTGRES_DB = os.getenv("POSTGRES_DB", "legal_assistant")
        self.POSTGRES_USER = os.getenv("POSTGRES_USER", "legal_assistant")
        self.POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")
        self.POSTGRES_HOST = os.getenv("POSTGRES_HOST", "127.0.0.1")
        self.POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5433")

        database_url = os.getenv("DATABASE_URL")

        self.DATABASE_URL = database_url or URL.create(
            drivername="postgresql+asyncpg",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_HOST,
            port=int(self.POSTGRES_PORT),
            database=self.POSTGRES_DB,
        )

        self.ML_SERVICE_URL = os.getenv(
            "ML_SERVICE_URL",
            "http://localhost:8001",
        )


settings = Settings()
