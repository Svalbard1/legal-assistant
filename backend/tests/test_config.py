from sqlalchemy.engine import URL

from app.config import Settings


def test_database_url_is_sqlalchemy_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("POSTGRES_USER", "test_user")
    monkeypatch.setenv("POSTGRES_PASSWORD", "test@:/?#%")
    monkeypatch.setenv("POSTGRES_HOST", "localhost")
    monkeypatch.setenv("POSTGRES_PORT", "5433")
    monkeypatch.setenv("POSTGRES_DB", "test_db")

    settings = Settings()

    assert isinstance(settings.DATABASE_URL, URL)
    assert settings.DATABASE_URL.drivername == "postgresql+asyncpg"
    assert settings.DATABASE_URL.password == "test@:/?#%"
    assert settings.DATABASE_URL.host == "localhost"
    assert settings.DATABASE_URL.database == "test_db"


def test_database_url_environment_variable_has_priority(monkeypatch):
    custom_url = "postgresql+asyncpg://custom_user:custom_pass@db.example.com:5432/custom_db"

    monkeypatch.setenv("DATABASE_URL", custom_url)

    settings = Settings()

    assert settings.DATABASE_URL == custom_url
