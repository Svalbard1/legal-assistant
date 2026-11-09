"""Smoke-тесты HTTP API (контракт v0.1) на фейковом энкодере.

Модель bge-m3 НЕ загружается: get_model подменяется детерминированной
заглушкой. Проверяется связка FastAPI + Qdrant(local) + ingest-логика:
статусы, валидация, идемпотентность /ingest (нет дубликатов).
"""

import hashlib
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient

import service

DIM = 1024
SAMPLE = Path(__file__).resolve().parents[1] / "data" / "sample" / "пример.txt"


def _vec(text: str) -> np.ndarray:
    """Детерминированный псевдовектор: одинаковый текст -> одинаковый вектор."""
    seed = int.from_bytes(hashlib.md5(text.encode("utf-8")).digest()[:8], "little")
    v = np.random.default_rng(seed).random(DIM)
    return v / np.linalg.norm(v)


class FakeModel:
    """Подмена sentence-transformers: мгновенно и предсказуемо."""

    def encode(self, texts):
        if isinstance(texts, str):
            return _vec(texts)
        return np.stack([_vec(t) for t in texts])


@pytest.fixture()
def api(monkeypatch, tmp_path):
    qc = QdrantClient(path=str(tmp_path / "db"))
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    monkeypatch.setattr(service, "get_model", lambda: FakeModel())
    monkeypatch.setattr(service, "get_client", lambda: qc)
    monkeypatch.setattr(service, "UPLOAD_DIR", uploads)
    return TestClient(service.app)


def _ingest_sample(api):
    with open(SAMPLE, "rb") as f:
        return api.post("/ingest", files={"file": ("пример.txt", f, "text/plain")})


def test_health_before_ingest(api):
    body = api.get("/health").json()
    assert body["status"] == "ok"
    assert body["chunks_indexed"] == 0
    assert body["llm"] == "stub"
    assert body["embed_model"] == "BAAI/bge-m3"


def test_ask_before_ingest_503(api):
    r = api.post("/ask", json={"question": "что по договору поставки"})
    assert r.status_code == 503


def test_ingest_and_ask_roundtrip(api):
    r = _ingest_sample(api)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "indexed"
    assert body["filename"] == "пример.txt"
    assert body["chunks"] > 0
    assert len(body["doc_id"]) == 32

    r = api.post("/ask", json={"question": "неустойка за просрочку поставки", "top_k": 2})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["llm"] == "stub"
    assert isinstance(body["took_ms"], int)
    assert len(body["sources"]) == 2
    assert body["sources"][0]["file"] == "пример.txt"
    assert set(body["sources"][0]) == {"file", "text", "score"}
    assert body["answer"].startswith("Вопрос:")


def test_reingest_same_file_no_duplicates(api):
    _ingest_sample(api)
    n1 = api.get("/health").json()["chunks_indexed"]
    _ingest_sample(api)          # тот же файл повторно
    n2 = api.get("/health").json()["chunks_indexed"]
    assert n1 == n2, "повторный ingest не должен увеличивать индекс"


def test_ask_validation_422(api):
    assert api.post("/ask", json={"question": "аб"}).status_code == 422           # < 3 символов
    assert api.post("/ask", json={"question": "норм вопрос", "top_k": 0}).status_code == 422
    assert api.post("/ask", json={"question": "норм вопрос", "top_k": 21}).status_code == 422
    assert api.post("/ask", json={}).status_code == 422


def test_ingest_wrong_format_400(api):
    r = api.post("/ingest", files={"file": ("shell.exe", b"MZ fake", "application/octet-stream")})
    assert r.status_code == 400


def test_ingest_empty_text_400(api):
    r = api.post("/ingest", files={"file": ("empty.txt", b"  \n\t ", "text/plain")})
    assert r.status_code == 400


def test_ingest_too_large_413(api):
    big = b"x" * (26 * 1024 * 1024)
    r = api.post("/ingest", files={"file": ("big.txt", big, "text/plain")})
    assert r.status_code == 413
