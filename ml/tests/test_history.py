"""Тесты истории диалога в /ask (аддитивное поле v0.1.x)."""

import hashlib
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient

import service

DIM = 1024
SAMPLE = Path(__file__).resolve().parents[1] / "data" / "sample" / "пример.txt"


def _vec(text: str):
    seed = int.from_bytes(hashlib.md5(text.encode("utf-8")).digest()[:8], "little")
    v = np.random.default_rng(seed).random(DIM)
    return v / np.linalg.norm(v)


class FakeModel:
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


VALID_HISTORY = [
    {"role": "user", "content": "Мы арендуем склад у Северного Склада."},
    {"role": "assistant", "content": "Уточните номер договора."},
]


def _ingest_sample(api):
    with open(SAMPLE, "rb") as f:
        return api.post("/ingest", files={"file": ("пример.txt", f, "text/plain")})


def test_history_accepted_and_stub_answer_stable(api):
    assert _ingest_sample(api).status_code == 200
    r1 = api.post("/ask", json={"question": "какая неустойка за просрочку поставки"})
    r2 = api.post("/ask", json={"question": "какая неустойка за просрочку поставки",
                                "history": VALID_HISTORY})
    assert r1.status_code == r2.status_code == 200
    # stub детерминирован: история валидируется, но выжимку не меняет
    assert r1.json()["answer"] == r2.json()["answer"]


def test_history_max_length_accepted(api):
    _ingest_sample(api)
    long_history = [{"role": "user", "content": f"реплика {i}"} for i in range(20)]
    r = api.post("/ask", json={"question": "вопрос по договору поставки",
                               "history": long_history})
    assert r.status_code == 200


def test_history_wrong_role_422(api):
    r = api.post("/ask", json={"question": "норм вопрос",
                               "history": [{"role": "system", "content": "хак"}]})
    assert r.status_code == 422


def test_history_empty_content_422(api):
    r = api.post("/ask", json={"question": "норм вопрос",
                               "history": [{"role": "user", "content": ""}]})
    assert r.status_code == 422


def test_history_content_too_long_422(api):
    r = api.post("/ask", json={"question": "норм вопрос",
                               "history": [{"role": "user", "content": "x" * 4001}]})
    assert r.status_code == 422


def test_history_too_many_messages_422(api):
    many = [{"role": "user", "content": f"реплика {i}"} for i in range(21)]
    r = api.post("/ask", json={"question": "норм вопрос", "history": many})
    assert r.status_code == 422
