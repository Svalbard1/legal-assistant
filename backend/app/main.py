from datetime import datetime, timedelta, timezone
from uuid import UUID
import httpx
from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.ml_client import ml_client
from app.models import ChatSession, Message, MessageSource
from app.schemas import (
    AskRequest,
    AskResponse,
    MessageListResponse,
    MessageResponse,
    MessageSourceResponse,
    SessionListResponse,
    SessionResponse,
)


app = FastAPI(
    title="Legal Assistant Backend",
    version="0.1.0",
)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/ask", response_model=AskResponse)
async def ask(
    request: AskRequest,
    db: AsyncSession = Depends(get_db),
):
    # Проверяем диалог и загружаем историю, если это продолжение чата.
    if request.session_id is not None:
        chat_session = await db.get(ChatSession, request.session_id)

        if chat_session is None:
            raise HTTPException(
                status_code=404,
                detail="Chat session not found",
            )

        result = await db.execute(
            select(Message)
            .where(Message.session_id == request.session_id)
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(20)
        )
        previous_messages = list(reversed(result.scalars().all()))

        history = [
            {"role": message.role, "content": message.content}
            for message in previous_messages
        ]
    else:
        chat_session = None
        history = []

    # Получаем ответ ML. До успешного ответа ничего не записываем в БД.
    try:
        result = await ml_client.ask(
            question=request.question,
            top_k=request.top_k,
            history=history,
        )

    except httpx.HTTPStatusError as exc:
        try:
            payload = exc.response.json()
            detail = (
                payload.get("detail", "ML service returned an error")
                if isinstance(payload, dict)
                else "ML service returned an error"
            )
        except ValueError:
            detail = "ML service returned an error"

        raise HTTPException(
            status_code=exc.response.status_code,
            detail=detail,
        )

    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="ML service timed out",
        )

    except httpx.RequestError:
        raise HTTPException(
            status_code=502,
            detail="ML service is unavailable",
        )

    # Создаём новый диалог только после успешного ответа ML.
    if chat_session is None:
        chat_session = ChatSession(title=request.question[:255])
        db.add(chat_session)
        await db.flush()
    else:
        chat_session.updated_at = datetime.now(timezone.utc)

    # Фиксируем время сообщений отдельно,
    # чтобы сохранить правильный порядок в истории.
    message_time = datetime.now(timezone.utc)

    # Сохраняем вопрос пользователя.
    user_message = Message(
        session_id=chat_session.id,
        role="user",
        content=request.question,
        created_at=message_time,
    )
    db.add(user_message)

    # Сохраняем ответ ассистента чуть позже вопроса.
    assistant_message = Message(
        session_id=chat_session.id,
        role="assistant",
        content=result["answer"],
        took_ms=result["took_ms"],
        llm=result["llm"],
        created_at=message_time + timedelta(microseconds=1),
    )
    db.add(assistant_message)
    await db.flush()

    # Сохраняем источники ответа с их исходным порядком.
    for position, source in enumerate(result["sources"], start=1):
        db.add(
            MessageSource(
                message_id=assistant_message.id,
                position=position,
                file=source["file"],
                text=source["text"],
                score=source["score"],
                page=source.get("page"),
            )
        )

    await db.commit()

    return AskResponse(
        session_id=chat_session.id,
        answer=result["answer"],
        sources=result["sources"],
        took_ms=result["took_ms"],
        llm=result["llm"],
    )
@app.get("/api/sessions", response_model=SessionListResponse)
async def list_sessions(
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ChatSession).order_by(ChatSession.updated_at.desc())
    )
    sessions = result.scalars().all()

    return SessionListResponse(
        sessions=[
            SessionResponse(
                id=session.id,
                title=session.title,
                created_at=session.created_at,
                updated_at=session.updated_at,
            )
            for session in sessions
        ]
    )
@app.get(
    "/api/sessions/{session_id}/messages",
    response_model=MessageListResponse,
)
async def get_session_messages(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    chat_session = await db.get(ChatSession, session_id)

    if chat_session is None:
        raise HTTPException(
            status_code=404,
            detail="Chat session not found",
        )

    result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at, Message.id)
    )
    messages = result.scalars().all()

    message_ids = [message.id for message in messages]

    sources_by_message = {message_id: [] for message_id in message_ids}

    if message_ids:
        sources_result = await db.execute(
            select(MessageSource)
            .where(MessageSource.message_id.in_(message_ids))
            .order_by(MessageSource.message_id, MessageSource.position)
        )

        for source in sources_result.scalars().all():
            sources_by_message[source.message_id].append(
                MessageSourceResponse(
                    position=source.position,
                    file=source.file,
                    text=source.text,
                    score=source.score,
                    page=source.page,
                )
            )

    return MessageListResponse(
        session_id=session_id,
        messages=[
            MessageResponse(
                id=message.id,
                role=message.role,
                content=message.content,
                created_at=message.created_at,
                sources=sources_by_message[message.id],
                took_ms=message.took_ms,
                llm=message.llm,
            )
            for message in messages
        ],
    )
