"""Тесты генерации v0.2: OpenAI-совместимый прокси через env, fallback на stub.

Прокси поднимается локальным mock-сервером (/chat/completions). Проверяется:
- /health и /ask показывают llm="vllm", когда задан LLM_API_URL;
- /ask возвращает настоящий текст LLM;
- прокси упал -> детерминированный fallback (llm="stub"), сабмит не ломается;
- слабый ретрив -> прямой отказ (REFUSAL), формулировка контракта.
"""

import json
import threading
import typing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient

import service

DIM = 1024
SAMPLE = Path(__file__).resolve().parents[1] / "data" / "sample" / "пример.txt"


def _vec(text: str) -> np.ndarray:
    import hashlib
    seed = int.from_bytes(hashlib.md5(text.encode("utf-8")).digest()[:8], "little")
    v = np.random.default_rng(seed).random(DIM)
    return v / np.linalg.norm(v)


class FakeModel:
    def encode(self, texts):
        if isinstance(texts, str):
            return _vec(texts)
        return np.stack([_vec(t) for t in texts])


class _MockLLM(BaseHTTPRequestHandler):
    seen: typing.ClassVar[list] = []

    def log_message(self, *a):
        pass

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(n) or b"{}")
        _MockLLM.seen.append((self.path, payload))
        if self.path != "/chat/completions":
            self._json(404, {"error": "nf"})
            return
        if self.headers.get("Authorization") != "Bearer test-key":
            self._json(401, {"error": "bad key"})
            return
        self._json(200, {"choices": [{"message": {
            "role": "assistant",
            "content": "СГЕНЕРИРОВАННЫЙ ОТВЕТ: неустойка 0,1% в день (п. 4.1)."}}]})


@pytest.fixture()
def llm_server():
    _MockLLM.seen = []
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _MockLLM)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", _MockLLM
    srv.shutdown()


@pytest.fixture()
def api(monkeypatch, tmp_path):
    qc = QdrantClient(path=str(tmp_path / "db"))
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    monkeypatch.setattr(service, "get_model", lambda: FakeModel())
    monkeypatch.setattr(service, "get_client", lambda: qc)
    monkeypatch.setattr(service, "UPLOAD_DIR", uploads)
    monkeypatch.setattr(service, "_corpus_cache", [None, 0])
    return TestClient(service.app)


def _ingest_sample(api):
    with open(SAMPLE, "rb") as f:
        return api.post("/ingest", files={"file": ("пример.txt", f, "text/plain")})


def test_health_vllm_when_proxy_set(api, monkeypatch, llm_server):
    url, _mock = llm_server
    monkeypatch.setattr(service, "LLM_BASE_URL", url)
    assert api.get("/health").json()["llm"] == "vllm"


def test_ask_generates_via_proxy(api, monkeypatch, llm_server):
    url, mock = llm_server
    monkeypatch.setattr(service, "LLM_BASE_URL", url)
    monkeypatch.setattr(service, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(service, "LLM_MODEL", "deepseek/deepseek-v4.1-flash")
    assert _ingest_sample(api).status_code == 200

    r = api.post("/ask", json={"question": "неустойка за просрочку поставки", "top_k": 3})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["llm"] == "vllm"
    assert body["answer"].startswith("СГЕНЕРИРОВАННЫЙ ОТВЕТ")
    # в LLM ушли: модель, system-промпт, история отсутствует, контекст с документом
    path, payload = mock.seen[-1]
    assert path == "/chat/completions"
    assert payload["model"] == "deepseek/deepseek-v4.1-flash"
    assert payload["messages"][0]["role"] == "system"
    assert "юридический ассистент" in payload["messages"][0]["content"]
    assert "пример.txt" in payload["messages"][-1]["content"]


def test_ask_history_goes_to_llm(api, monkeypatch, llm_server):
    url, mock = llm_server
    monkeypatch.setattr(service, "LLM_BASE_URL", url)
    monkeypatch.setattr(service, "LLM_API_KEY", "test-key")
    assert _ingest_sample(api).status_code == 200

    r = api.post("/ask", json={
        "question": "а в каких случаях её можно снизить?",
        "history": [{"role": "user", "content": "какая неустойка по договору?"},
                    {"role": "assistant", "content": "0,1% в день."}]})
    body = r.json()
    assert body["llm"] == "vllm"
    roles = [m["role"] for m in mock.seen[-1][1]["messages"]]
    assert roles == ["system", "user", "assistant", "user"]


def test_ask_fallback_to_stub_when_proxy_dead(api, monkeypatch):
    monkeypatch.setattr(service, "LLM_BASE_URL", "http://127.0.0.1:9")   # закрытый порт
    monkeypatch.setattr(service, "HTTP_RETRIES", 0)                      # без ожидания
    assert _ingest_sample(api).status_code == 200

    r = api.post("/ask", json={"question": "неустойка за просрочку поставки"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["llm"] == "stub"
    assert body["answer"].startswith("Вопрос:")   # детерминированная выжимка


def test_ask_refusal_on_weak_retrieval(api, monkeypatch):
    monkeypatch.setattr(service, "REFUSAL_THRESHOLD", 1.5)   # выше любого косинуса
    assert _ingest_sample(api).status_code == 200

    r = api.post("/ask", json={"question": "неустойка за просрочку поставки"})
    body = r.json()
    assert body["answer"].startswith("Ответа нет в предоставленной базе знаний")
    assert body["sources"], "источники возвращаются и при отказе"
