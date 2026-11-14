import httpx
import pytest

from app.ml_client import MLClient


@pytest.mark.asyncio
async def test_ask_sends_history(monkeypatch):
    captured = {}

    def handler(request):
        captured["url"] = str(request.url)
        captured["json"] = __import__("json").loads(request.content)

        return httpx.Response(
            200,
            json={
                "answer": "Ответ",
                "sources": [],
                "took_ms": 100,
                "llm": "stub",
            },
        )

    original_async_client = httpx.AsyncClient

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original_async_client(
            transport=httpx.MockTransport(handler),
            **kwargs,
        ),
    )

    client = MLClient()
    result = await client.ask(
        question="Как взыскать неустойку?",
        top_k=5,
        history=[
            {"role": "user", "content": "Предыдущий вопрос"},
        ],
    )

    assert captured["url"].endswith("/ask")
    assert captured["json"] == {
        "question": "Как взыскать неустойку?",
        "top_k": 5,
        "history": [
            {"role": "user", "content": "Предыдущий вопрос"},
        ],
    }
    assert result["answer"] == "Ответ"
