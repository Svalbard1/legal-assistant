import httpx
import pytest
import pytest_asyncio

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.config import settings
from app.database import get_db
from app.main import app
from app.models import Document


@pytest_asyncio.fixture
async def client(db_session):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as test_client:
        yield test_client

    app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_ingest_saves_file_and_lists_document(
    client,
    db_session,
    monkeypatch,
    tmp_path,
):
    # Используем временную папку вместо настоящего uploads.
    monkeypatch.setattr(settings, "UPLOAD_DIR", tmp_path)

    content = b"test pdf content"

    async def fake_ingest(filename, content, content_type=None):
        assert filename == "contract.pdf"
        assert content == b"test pdf content"
        assert content_type == "application/pdf"

        return {
            "doc_id": "ml-test-id",
            "filename": filename,
            "chunks": 3,
            "status": "indexed",
        }

    monkeypatch.setattr(
        "app.main.ml_client.ingest",
        fake_ingest,
    )

    # Загружаем документ.
    response = await client.post(
        "/api/ingest",
        files={
            "file": (
                "contract.pdf",
                content,
                "application/pdf",
            )
        },
    )

    assert response.status_code == 200

    response_data = response.json()

    assert response_data["status"] == "indexed"
    assert response_data["filename"] == "contract.pdf"
    assert response_data["chunks"] == 3
    assert response_data["document_id"]

    # Проверяем запись в PostgreSQL.
    result = await db_session.execute(
        select(Document).where(
            Document.filename == "contract.pdf"
        )
    )

    document = result.scalar_one()

    assert document.status == "indexed"
    assert document.content_type == "application/pdf"
    assert document.size_bytes == len(content)
    assert document.storage_path

    # Проверяем, что оригинал действительно сохранён.
    stored_file = tmp_path / document.storage_path

    assert stored_file.exists()
    assert stored_file.is_file()
    assert stored_file.read_bytes() == content

    # Получаем список документов через GET.
    list_response = await client.get("/api/documents")

    assert list_response.status_code == 200

    documents = list_response.json()["documents"]

    assert len(documents) == 1
    assert documents[0]["id"] == str(document.id)
    assert documents[0]["filename"] == "contract.pdf"
    assert documents[0]["status"] == "indexed"
    assert documents[0]["chunks"] == 3


@pytest.mark.asyncio
async def test_ingest_ml_timeout_keeps_file_and_marks_failed(
    client,
    db_session,
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(settings, "UPLOAD_DIR", tmp_path)

    async def fake_ingest(**kwargs):
        raise httpx.TimeoutException("Timeout")

    monkeypatch.setattr(
        "app.main.ml_client.ingest",
        fake_ingest,
    )

    content = b"document content"

    response = await client.post(
        "/api/ingest",
        files={
            "file": (
                "failed.pdf",
                content,
                "application/pdf",
            )
        },
    )

    assert response.status_code == 504
    assert response.json()["detail"] == "ML service timed out"

    # Документ должен остаться в базе со статусом failed.
    result = await db_session.execute(
        select(Document).where(
            Document.filename == "failed.pdf"
        )
    )

    document = result.scalar_one()

    assert document.status == "failed"
    assert document.error_message == "ML service timed out"

    # Оригинал не должен удаляться при ошибке ML.
    stored_file = tmp_path / document.storage_path

    assert stored_file.exists()
    assert stored_file.read_bytes() == content