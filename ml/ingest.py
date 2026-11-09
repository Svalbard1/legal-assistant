"""Документы -> чанки -> эмбеддинги -> Qdrant (локальный режим).

Запуск из папки ml/:  python ingest.py
"""
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from sentence_transformers import SentenceTransformer

from config import (CHUNK_OVERLAP, CHUNK_SIZE, COLLECTION, DATA_DIR,
                    EMBED_MODEL, QDRANT_PATH)


def read_text(path: Path) -> str:
    """Текст из pdf / docx / txt / md."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        from pypdf import PdfReader
        return "\\n".join(p.extract_text() or "" for p in PdfReader(str(path)).pages)
    if suffix == ".docx":
        import docx
        return "\\n".join(p.text for p in docx.Document(str(path)).paragraphs)
    return path.read_text(encoding="utf-8")


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Режем на перекрывающиеся куски, стараясь не рвать предложения."""
    chunks, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            for sep in ("\\n", ". ", " "):
                cut = text.rfind(sep, start, end)
                if cut > start + size // 2:
                    end = cut + len(sep)
                    break
        chunks.append(text[start:end].strip())
        start = end - overlap if end < len(text) else end
    return [c for c in chunks if c]


def main() -> None:
    files = [p for p in DATA_DIR.iterdir()
             if p.suffix.lower() in {".pdf", ".docx", ".txt", ".md"}]
    if not files:
        print(f"Положи хотя бы один документ в {DATA_DIR} и запусти снова")
        return

    print(f"Загружаю {EMBED_MODEL} (первый раз скачается ~2 ГБ, подожди)...")
    model = SentenceTransformer(EMBED_MODEL)

    client = QdrantClient(path=str(QDRANT_PATH))   # без сервера, файл на диске
    if not client.collection_exists(COLLECTION):
        client.create_collection(
            COLLECTION, vectors_config=VectorParams(size=1024, distance=Distance.COSINE))

    point_id = 0
    for f in files:
        chunks = chunk_text(read_text(f))
        vectors = model.encode(chunks)
        client.upsert(COLLECTION, points=[
            PointStruct(id=point_id + i, vector=v.tolist(),
                        payload={"file": f.name, "text": c})
            for i, (c, v) in enumerate(zip(chunks, vectors))])
        point_id += len(chunks)
        print(f"  {f.name}: {len(chunks)} чанков")

    print(f"Готово: {point_id} чанков в '{COLLECTION}'")


if __name__ == "__main__":
    main()