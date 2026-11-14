import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")


class Settings:
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "legal_assistant")
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "legal_assistant")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "")
    POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "127.0.0.1")
    POSTGRES_PORT: str = os.getenv("POSTGRES_PORT", "5433")

    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        (
            f"postgresql+asyncpg://{POSTGRES_USER}:"
            f"{POSTGRES_PASSWORD}@{POSTGRES_HOST}:"
            f"{POSTGRES_PORT}/{POSTGRES_DB}"
        ),
    )

    ML_SERVICE_URL: str = os.getenv(
        "ML_SERVICE_URL",
        "http://localhost:8001",
    )


settings = Settings()
