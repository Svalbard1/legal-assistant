import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Settings:
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/legal_assistant",
    )
    ML_SERVICE_URL: str = os.getenv(
        "ML_SERVICE_URL",
        "http://localhost:8001",
    )


settings = Settings()
