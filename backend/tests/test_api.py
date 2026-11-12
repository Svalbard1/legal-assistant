import httpx
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_ask_success(monkeypatch):
    async def fake_ask(question, top_k=3, history=None):
        assert question == "Как взыскать неустойку?"
        assert top_k == 3
        assert history == [
            {"role": "user", "content": "Предыдущий вопрос"}
        ]

        return {
            "answer": "Ответ",
            "sources": [
                {
                    "file": "law.pdf",
                    "text": "Фрагмент закона",
                    "score": 0.9,
                    "page": 5,
                }
            ],
            "took_ms": 100,
            "llm": "stub",
        }

    monkeypatch.setattr("app.main.ml_client.ask", fake_ask)

    response = client.post(
        "/api/ask",
        json={
            "question": "Как взыскать неустойку?",
            "history": [
                {"role": "user", "content": "Предыдущий вопрос"}
            ],
        },
    )

    assert response.status_code == 200
    assert response.json()["sources"][0]["page"] == 5


def test_ask_invalid_history():
    response = client.post(
        "/api/ask",
        json={
            "question": "Как взыскать неустойку?",
            "history": [
                {"role": "system", "content": "Неверная роль"}
            ],
        },
    )

    assert response.status_code == 422


def test_ask_history_limit():
    response = client.post(
        "/api/ask",
        json={
            "question": "Как взыскать неустойку?",
            "history": [
                {"role": "user", "content": "Вопрос"}
                for _ in range(21)
            ],
        },
    )

    assert response.status_code == 422


def test_ask_ml_503(monkeypatch):
    async def fake_ask(**kwargs):
        request = httpx.Request("POST", "http://localhost:8001/ask")
        response = httpx.Response(
            503,
            json={"detail": "Индекс временно недоступен"},
            request=request,
        )
        raise httpx.HTTPStatusError(
            "Service unavailable",
            request=request,
            response=response,
        )

    monkeypatch.setattr("app.main.ml_client.ask", fake_ask)

    response = client.post(
        "/api/ask",
        json={"question": "Как взыскать неустойку?"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Индекс временно недоступен"


def test_ask_ml_timeout(monkeypatch):
    async def fake_ask(**kwargs):
        raise httpx.TimeoutException("Timeout")

    monkeypatch.setattr("app.main.ml_client.ask", fake_ask)

    response = client.post(
        "/api/ask",
        json={"question": "Как взыскать неустойку?"},
    )

    assert response.status_code == 504


def test_ask_ml_unavailable(monkeypatch):
    async def fake_ask(**kwargs):
        raise httpx.ConnectError("Connection refused")

    monkeypatch.setattr("app.main.ml_client.ask", fake_ask)

    response = client.post(
        "/api/ask",
        json={"question": "Как взыскать неустойку?"},
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "ML service is unavailable"
