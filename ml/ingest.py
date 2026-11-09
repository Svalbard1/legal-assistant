"""Документы -> чанки -> эмбеддинги -> Qdrant (локальный режим).

Запуск из папки ml/:  python ingest.py

Идемпотентность: повторный запуск НЕ создаёт дубликатов. Каждая точка
ключуется стабильным id (uuid5 по имени файла и номеру чанка), а перед
записью старые точки этого документа удаляются. Тот же механизм
использует HTTP-сервис (service.py, POST /ingest).
"""

import uuid
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import (Distance, FieldCondition, Filter,
                                  FilterSelector, MatchValue, PointStruct,
                                  VectorParams)

from config import (CHUNK_OVERLAP, CHUNK_SIZE, COLLECTION, DATA_DIR,
                    EMBED_MODEL, QDRANT_PATH)


def read_text(path: Path) -> str:
    """Текст из pdf / docx / txt / md."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        from pypdf import PdfReader

        return "\n".join(p.extract_text() or "" for p in PdfReader(str(path)).pages)
    if suffix == ".docx":
        import docx

        return "\n".join(p.text for p in docx.Document(str(path)).paragraphs)
    return path.read_text(encoding="utf-8")


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Режем на перекрывающиеся куски, стараясь не рвать предложения."""
    chunks, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            for sep in ("\n", ". ", " "):
                cut = text.rfind(sep, start, end)
                if cut > start + size // 2:
                    end = cut + len(sep)
                    break
        chunks.append(text[start:end].strip())
        start = end - overlap if end < len(text) else end
    return [c for c in chunks if c]


# --- Идентификация документов (общая для CLI и HTTP-сервиса) ---


def doc_id_for(filename: str) -> str:
    """Стабильный id документа: повторная загрузка файла с тем же именем
    даёт тот же doc_id -> документ обновляется, а не дублируется."""
    return uuid.uuid5(uuid.NAMESPACE_URL, f"legal-doc:{filename}").hex


def point_id_for(filename: str, idx: int) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"legal-point:{filename}:{idx}"))


def ensure_collection(client: QdrantClient) -> None:
    if not client.collection_exists(COLLECTION):
        client.create_collection(
            COLLECTION,
            vectors_config=VectorParams(size=1024, distance=Distance.COSINE))


def index_chunks(client: QdrantClient, *, filename: str,
                 chunks: list[str], vectors) -> int:
    """Идемпотентно кладёт чанки одного документа в индекс.

    Перед записью удаляет прежние точки этого doc_id, поэтому повторный
    ingest не плодит дубликаты. Возвращает число записанных чанков.
    """
    ensure_collection(client)
    doc_id = doc_id_for(filename)
    client.delete(COLLECTION, points_selector=FilterSelector(
        filter=Filter(must=[FieldCondition(key="doc_id",
                                           match=MatchValue(value=doc_id))])))
    client.upsert(COLLECTION, points=[
        PointStruct(id=point_id_for(filename, i), vector=v.tolist(),
                    payload={"doc_id": doc_id, "file": filename, "text": c})
        for i, (c, v) in enumerate(zip(chunks, vectors))])
    return len(chunks)


def main() -> None:
    files = [p for p in DATA_DIR.iterdir()
             if p.suffix.lower() in {".pdf", ".docx", ".txt", ".md"}]
    if not files:
        print(f"Положи хотя бы один документ в {DATA_DIR} и запусти снова")
        return

    print(f"Загружаю {EMBED_MODEL} (первый раз скачается ~2 ГБ, подожди)...")
    from sentence_transformers import SentenceTransformer  # тяжёлый импорт — лениво

    model = SentenceTransformer(EMBED_MODEL)
    client = QdrantClient(path=str(QDRANT_PATH))   # без сервера, файл на диске

    total = 0
    for f in sorted(files):
        chunks = chunk_text(read_text(f))
        if not chunks:
            print(f"  {f.name}: текста нет, пропущен")
            continue
        vectors = model.encode(chunks)
        index_chunks(client, filename=f.name, chunks=chunks, vectors=vectors)
        total += len(chunks)
        print(f"  {f.name}: {len(chunks)} чанков")

    indexed = client.count(COLLECTION, exact=True).count
    print(f"Готово: {total} чанков записано, всего точек в '{COLLECTION}': {indexed}")


if __name__ == "__main__":
    main()
