
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4
from fastapi.middleware.cors import CORSMiddleware
import httpx
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.ml_client import ml_client
from app.models import (
    ChatSession,
    Document,
    Message,
    MessageSource,
)
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

ALLOWED_SUFFIXES = {".pdf", ".docx", ".txt", ".md"}
MAX_UPLOAD_MB = 25
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024


@app.get("/health")
async def health():
    return {"status": "ok"}


async def mark_document_failed(
    db: AsyncSession,
    document: Document,
    detail: str,
):
    document.status = "failed"
    document.error_message = str(detail)[:2000]

    await db.commit()


@app.post("/api/ingest")
async def ingest_document(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    # Проверяем имя и расширение файла.
    filename = (
        (file.filename or "")
        .replace("\\", "/")
        .split("/")[-1]
    )
    suffix = Path(filename).suffix.lower()

    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Формат '{suffix or 'без расширения'}' "
                "не поддерживается. "
                "Разрешены: .docx, .md, .pdf, .txt"
            ),
        )

    if len(filename) > 255:
        raise HTTPException(
            status_code=400,
            detail="Имя файла слишком длинное",
        )

    # Читаем максимум 25 МБ и ещё один байт.
    content = await file.read(MAX_UPLOAD_BYTES + 1)

    if not content:
        raise HTTPException(
            status_code=400,
            detail="Файл пустой",
        )

    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Файл больше {MAX_UPLOAD_MB} МБ",
        )

    # Генерируем уникальное имя физического файла.
    storage_filename = f"{uuid4().hex}{suffix}"

    upload_dir = Path(settings.UPLOAD_DIR)
    storage_file = upload_dir / storage_filename

    # Сохраняем оригинал на диск.
    try:
        await asyncio.to_thread(
            upload_dir.mkdir,
            parents=True,
            exist_ok=True,
        )

        await asyncio.to_thread(
            storage_file.write_bytes,
            content,
        )

    except OSError:
        raise HTTPException(
            status_code=500,
            detail="Не удалось сохранить файл",
        )

    # Создаём запись в PostgreSQL.
    document = Document(
        filename=filename,
        storage_path=storage_filename,
        content_type=file.content_type,
        size_bytes=len(content),
        status="processing",
    )

    db.add(document)

    try:
        await db.commit()
        await db.refresh(document)

    except Exception:
        await db.rollback()

        await asyncio.to_thread(
            storage_file.unlink,
            missing_ok=True,
        )

        raise HTTPException(
            status_code=500,
            detail="Не удалось сохранить сведения о документе",
        )

    # Отправляем оригинал в ML для индексации.
    try:
        ml_result = await ml_client.ingest(
            filename=filename,
            content=content,
            content_type=file.content_type,
        )

    except httpx.HTTPStatusError as exc:
        try:
            payload = exc.response.json()
            detail = (
                payload.get(
                    "detail",
                    "ML service returned an error",
                )
                if isinstance(payload, dict)
                else "ML service returned an error"
            )
        except ValueError:
            detail = "ML service returned an error"

        await mark_document_failed(
            db,
            document,
            detail,
        )

        raise HTTPException(
            status_code=exc.response.status_code,
            detail=detail,
        )

    except httpx.TimeoutException:
        detail = "ML service timed out"

        await mark_document_failed(
            db,
            document,
            detail,
        )

        raise HTTPException(
            status_code=504,
            detail=detail,
        )

    except httpx.RequestError:
        detail = "ML service is unavailable"

        await mark_document_failed(
            db,
            document,
            detail,
        )

        raise HTTPException(
            status_code=502,
            detail=detail,
        )

    # Обновляем данные после успешной индексации.
    document.status = "indexed"
    document.ml_doc_id = ml_result.get("doc_id")
    document.chunks = ml_result.get("chunks")
    document.error_message = None

    await db.commit()

    return {
        **ml_result,
        "document_id": str(document.id),
        "filename": filename,
        "status": document.status,
    }


@app.get("/api/documents")
async def list_documents(
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Document).order_by(Document.created_at.desc())
    )

    documents = result.scalars().all()

    return {
        "documents": [
            {
                "id": str(document.id),
                "filename": document.filename,
                "content_type": document.content_type,
                "size_bytes": document.size_bytes,
                "status": document.status,
                "chunks": document.chunks,
                "created_at": document.created_at,
            }
            for document in documents
        ]
    }


@app.post("/api/ask", response_model=AskResponse)
async def ask(
    request: AskRequest,
    db: AsyncSession = Depends(get_db),
):
    if request.session_id is not None:
        chat_session = await db.get(
            ChatSession,
            request.session_id,
        )

        if chat_session is None:
            raise HTTPException(
                status_code=404,
                detail="Chat session not found",
            )

        result = await db.execute(
            select(Message)
            .where(Message.session_id == request.session_id)
            .order_by(
                Message.created_at.desc(),
                Message.id.desc(),
            )
            .limit(20)
        )

        previous_messages = list(
            reversed(result.scalars().all())
        )

        history = [
            {
                "role": message.role,
                "content": message.content,
            }
            for message in previous_messages
        ]

    else:
        chat_session = None
        history = []

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
                payload.get(
                    "detail",
                    "ML service returned an error",
                )
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

    if chat_session is None:
        chat_session = ChatSession(
            title=request.question[:255]
        )

        db.add(chat_session)
        await db.flush()

    else:
        chat_session.updated_at = datetime.now(timezone.utc)

    message_time = datetime.now(timezone.utc)

    user_message = Message(
        session_id=chat_session.id,
        role="user",
        content=request.question,
        created_at=message_time,
    )

    db.add(user_message)

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

    for position, source in enumerate(
        result["sources"],
        start=1,
    ):
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


@app.get(
    "/api/sessions",
    response_model=SessionListResponse,
)
async def list_sessions(
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ChatSession).order_by(
            ChatSession.updated_at.desc()
        )
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
    chat_session = await db.get(
        ChatSession,
        session_id,
    )

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

    message_ids = [
        message.id
        for message in messages
    ]

    sources_by_message = {
        message_id: []
        for message_id in message_ids
    }

    if message_ids:
        sources_result = await db.execute(
            select(MessageSource)
            .where(
                MessageSource.message_id.in_(message_ids)
            )
            .order_by(
                MessageSource.message_id,
                MessageSource.position,
            )
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
