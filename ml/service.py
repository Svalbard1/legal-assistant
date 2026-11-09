"""HTTP-сервис ML: POST /ingest, POST /ask, GET /health.

Контракт v0.1: ml/docs/API_CONTRACT.md.
Правило команды: менять контракт и этот файл только вместе, через PR
(ревьюят ml и backend).

Запуск (из папки ml/):   uvicorn service:app --port 8001
Swagger:                 http://localhost:8001/docs
ВАЖНО: ровно один процесс — uvicorn БЕЗ --workers и без replicas:
локальное хранилище Qdrant рассчитано на одного владельца файла.
"""

import os
import threading
import time
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from config import COLLECTION, EMBED_MODEL, QDRANT_PATH, TOP_K, UPLOAD_DIR
from ingest import chunk_text, doc_id_for, index_chunks, read_text

MAX_UPLOAD_MB = 25
ALLOWED_SUFFIXES = {".pdf", ".docx", ".txt", ".md"}
LLM_API_URL = os.environ.get("LLM_API_URL", "")   # задана -> llm="vllm", иначе "stub"

app = FastAPI(
    title="Legal Assistant — ML service",
    description="Поиск по документам (RAG). Контракт: ml/docs/API_CONTRACT.md",
    version="0.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # dev-режим; X-API-Key зарезервирован на v0.2
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Схемы контракта v0.1 ---


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    top_k: int = Field(default=TOP_K, ge=1, le=20)


class Source(BaseModel):
    file: str
    text: str
    score: float


class AskResponse(BaseModel):
    answer: str
    sources: list[Source]
    took_ms: int
    llm: str


class IngestResponse(BaseModel):
    doc_id: str
    filename: str
    chunks: int
    status: str


class HealthResponse(BaseModel):
    status: str
    chunks_indexed: int
    embed_model: str
    llm: str


# --- Тяжёлые объекты: ленивая инициализация при первом запросе ---

_model = None
_client = None
_init_lock = threading.Lock()


def get_model():
    """Модель эмбеддингов (первая загрузка ~5-20 с)."""
    global _model
    if _model is None:
        with _init_lock:
            if _model is None:      # double-checked locking
                from sentence_transformers import SentenceTransformer

                _model = SentenceTransformer(EMBED_MODEL)
    return _model


def get_client():
    """Qdrant в локальном режиме (файл на диске, без сервера)."""
    global _client
    if _client is None:
        with _init_lock:
            if _client is None:
                from qdrant_client import QdrantClient

                _client = QdrantClient(path=str(QDRANT_PATH))
    return _client


def llm_flag() -> str:
    return "vllm" if LLM_API_URL else "stub"


def llm_stub(question: str, sources: list[Source]) -> str:
    """Заглушка генерации до подключения vLLM: выжимка найденных фрагментов."""
    lines = [
        f"Вопрос: {question}",
        "",
        f"Найдено {len(sources)} фрагментов. Генерация LLM ещё не подключена "
        "(llm=stub), ниже — выдержки из источников:",
    ]
    for i, s in enumerate(sources, 1):
        lines.append(f"{i}. [{s.file}, score={s.score}] {s.text[:200].strip()}...")
    return "\n".join(lines)


# --- Эндпоинты ---


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Живость сервиса и размер индекса. Дёшево, можно дёргать часто."""
    chunks = 0
    try:
        client = get_client()
        if client.collection_exists(COLLECTION):
            chunks = client.count(COLLECTION, exact=True).count
    except Exception:
        pass  # индекс занят другим процессом и т.п. — сервис жив, счётчик 0
    return HealthResponse(status="ok", chunks_indexed=chunks,
                          embed_model=EMBED_MODEL, llm=llm_flag())


@app.post("/ingest", response_model=IngestResponse)
def ingest(file: UploadFile = File(...)) -> IngestResponse:
    """Документ -> чанки -> эмбеддинги -> индекс. Синхронный (v0.1); async — v0.2.

    Идемпотентно: файл с тем же именем обновляет документ (doc_id стабильный),
    дубликаты чанков не создаются.
    """
    filename = Path(file.filename or "").name     # голое имя, без пути
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(
            400, f"Формат '{suffix or 'без расширения'}' не поддерживается. "
                 f"Разрешены: {', '.join(sorted(ALLOWED_SUFFIXES))}")

    data = file.file.read()
    if not data:
        raise HTTPException(400, "Файл пустой")
    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"Файл больше {MAX_UPLOAD_MB} МБ")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    path = UPLOAD_DIR / filename
    path.write_bytes(data)

    try:
        text = read_text(path)
    except Exception as e:
        raise HTTPException(400, f"Не удалось прочитать файл: {e}") from e

    chunks = chunk_text(text)
    if not chunks:
        raise HTTPException(
            400, "В файле не найден текст (пустой документ или скан без текстового слоя)")

    vectors = get_model().encode(chunks)
    try:
        n_chunks = index_chunks(get_client(), filename=filename,
                                chunks=chunks, vectors=vectors)
    except Exception as e:
        raise HTTPException(500, f"Ошибка индексации: {e}") from e

    return IngestResponse(doc_id=doc_id_for(filename), filename=filename,
                          chunks=n_chunks, status="indexed")


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest) -> AskResponse:
    """Вопрос -> топ-K фрагментов + ответ (пока выжимка источников, llm=stub)."""
    t0 = time.monotonic()
    client = get_client()
    if not client.collection_exists(COLLECTION):
        raise HTTPException(503, "Индекс пуст — сначала загрузите документы через /ingest")

    vec = get_model().encode(req.question).tolist()
    hits = client.query_points(COLLECTION, query=vec, limit=req.top_k).points

    sources = [Source(file=h.payload.get("file", "?"),
                      text=h.payload.get("text", ""),
                      score=round(h.score, 4))
               for h in hits]
    if not sources:
        raise HTTPException(404, "По запросу ничего не найдено")

    return AskResponse(
        answer=llm_stub(req.question, sources),
        sources=sources,
        took_ms=int((time.monotonic() - t0) * 1000),
        llm=llm_flag(),
    )
