import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from datetime import datetime, timedelta, timezone
from app.database import get_db
from app.main import app
from app.models import ChatSession, Message, MessageSource


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
async def test_ask_success(client, db_session, monkeypatch):
    chat_session = ChatSession(title="Предыдущий диалог")
    db_session.add(chat_session)
    await db_session.flush()

    db_session.add(
        Message(
            session_id=chat_session.id,
            role="user",
            content="Предыдущий вопрос",
        )
    )
    await db_session.flush()

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

    response = await client.post(
        "/api/ask",
        json={
            "session_id": str(chat_session.id),
            "question": "Как взыскать неустойку?",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == str(chat_session.id)
    assert data["answer"] == "Ответ"
    assert data["sources"][0]["page"] == 5

    messages = (
        await db_session.execute(
            select(Message)
            .where(Message.session_id == chat_session.id)
            .order_by(Message.created_at, Message.id)
        )
    ).scalars().all()

    assert len(messages) == 3
    assert messages[-2].role == "user"
    assert messages[-1].role == "assistant"

    sources = (
        await db_session.execute(
            select(MessageSource).where(
                MessageSource.message_id == messages[-1].id
            )
        )
    ).scalars().all()

    assert len(sources) == 1
    assert sources[0].file == "law.pdf"
    assert sources[0].page == 5


@pytest.mark.asyncio
async def test_ask_creates_new_session(client, db_session, monkeypatch):
    async def fake_ask(**kwargs):
        assert kwargs["history"] == []
        return {
            "answer": "Ответ",
            "sources": [],
            "took_ms": 50,
            "llm": "stub",
        }

    monkeypatch.setattr("app.main.ml_client.ask", fake_ask)

    response = await client.post(
        "/api/ask",
        json={"question": "Как взыскать неустойку?"},
    )

    assert response.status_code == 200
    session_id = response.json()["session_id"]

    chat_session = await db_session.get(
        ChatSession,
        session_id,
    )
    assert chat_session is not None
    assert chat_session.title == "Как взыскать неустойку?"

    messages = (
        await db_session.execute(
            select(Message).where(Message.session_id == session_id)
        )
    ).scalars().all()

    assert len(messages) == 2


@pytest.mark.asyncio
async def test_ask_unknown_session(client, monkeypatch):
    response = await client.post(
        "/api/ask",
        json={
            "session_id": "00000000-0000-0000-0000-000000000001",
            "question": "Как взыскать неустойку?",
        },
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_ask_invalid_question(client):
    response = await client.post(
        "/api/ask",
        json={"question": "??"},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_ask_ml_503(client, monkeypatch):
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

    response = await client.post(
        "/api/ask",
        json={"question": "Как взыскать неустойку?"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Индекс временно недоступен"


@pytest.mark.asyncio
async def test_ask_ml_timeout(client, monkeypatch):
    async def fake_ask(**kwargs):
        raise httpx.TimeoutException("Timeout")

    monkeypatch.setattr("app.main.ml_client.ask", fake_ask)

    response = await client.post(
        "/api/ask",
        json={"question": "Как взыскать неустойку?"},
    )

    assert response.status_code == 504


@pytest.mark.asyncio
async def test_ask_ml_unavailable(client, monkeypatch):
    async def fake_ask(**kwargs):
        raise httpx.ConnectError("Connection refused")

    monkeypatch.setattr("app.main.ml_client.ask", fake_ask)

    response = await client.post(
        "/api/ask",
        json={"question": "Как взыскать неустойку?"},
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "ML service is unavailable"
@pytest.mark.asyncio
async def test_list_sessions(client, db_session):
    first_session = ChatSession(title="Первый диалог")
    second_session = ChatSession(title="Второй диалог")

    db_session.add_all([first_session, second_session])
    await db_session.flush()

    response = await client.get("/api/sessions")

    assert response.status_code == 200

    data = response.json()
    assert len(data["sessions"]) == 2

    titles = [session["title"] for session in data["sessions"]]
    assert set(titles) == {"Первый диалог", "Второй диалог"}

    for session in data["sessions"]:
        assert "id" in session
        assert "created_at" in session
        assert "updated_at" in session
@pytest.mark.asyncio
async def test_get_session_messages(client, db_session):
    chat_session = ChatSession(title="Тестовый диалог")
    db_session.add(chat_session)
    await db_session.flush()

    message_time = datetime.now(timezone.utc)
    user_message = Message(
        created_at=message_time,
        session_id=chat_session.id,
        role="user",
        content="Как взыскать неустойку?",
    )
    assistant_message = Message(
        created_at=message_time + timedelta(microseconds=1),
        session_id=chat_session.id,
        role="assistant",
        content="Можно обратиться в суд.",
        took_ms=120,
        llm="stub",
    )

    db_session.add_all([user_message, assistant_message])
    await db_session.flush()

    db_session.add(
        MessageSource(
            message_id=assistant_message.id,
            position=1,
            file="law.pdf",
            text="Фрагмент закона",
            score=0.95,
            page=5,
        )
    )
    await db_session.flush()

    response = await client.get(
        f"/api/sessions/{chat_session.id}/messages"
    )

    assert response.status_code == 200

    data = response.json()
    assert data["session_id"] == str(chat_session.id)
    assert len(data["messages"]) == 2

    assert data["messages"][0]["role"] == "user"
    assert data["messages"][0]["content"] == "Как взыскать неустойку?"
    assert data["messages"][0]["sources"] == []

    assistant = data["messages"][1]
    assert assistant["role"] == "assistant"
    assert assistant["content"] == "Можно обратиться в суд."
    assert assistant["took_ms"] == 120
    assert assistant["llm"] == "stub"

    assert len(assistant["sources"]) == 1
    assert assistant["sources"][0]["file"] == "law.pdf"
    assert assistant["sources"][0]["page"] == 5
    assert assistant["sources"][0]["position"] == 1
@pytest.mark.asyncio
async def test_get_messages_unknown_session(client):
    response = await client.get(
        "/api/sessions/00000000-0000-0000-0000-000000000001/messages"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Chat session not found"
