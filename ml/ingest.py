"""Документы -> структурные чанки -> эмбеддинги -> Qdrant (локальный режим). v2

Запуск из папки ml/:  python ingest.py

Чанкинг v2 (структурный): текст разбивается на секции по заголовкам и нумерованным
пунктам ("1. ПРЕДМЕТ ДОГОВОРА", "4.1. ...", "Статья N"), секции пакуются в чанки
<=CHUNK_SIZE, крупные секции режутся с перекрытием (chunk_text). Каждый чанк несёт
номер страницы источника -> payload["page"] (готовность к sources[].page).

Идемпотентность: точки ключуются стабильным id (uuid5 по имени файла и номеру чанка),
перед записью старые точки документа удаляются. Тот же контракт у HTTP-сервиса.
"""

import os
import re
import uuid
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PointStruct,
    VectorParams,
)

from config import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    COLLECTION,
    DATA_DIR,
    EMBED_MODEL,
    QDRANT_PATH,
)

# Заголовок/начало пункта: "1. ПРЕДМЕТ ДОГОВОРА", "4.1. За просрочку...", "Статья 5"
HEADER_RE = re.compile(r"^\s*(?:\d+(?:\.\d+)*\.?\s+\S|статья\s+\d+\.?\s)", re.IGNORECASE)

CHUNKER_MODE = os.environ.get("CHUNKER", "dense")  # dense | dense_pages | structured


def read_text(path: Path) -> str:
    """Весь текст файла одной строкой (совместимость/отладка)."""
    return "\n".join(text for _page, text in read_text_pages(path))


def read_text_pages(path: Path) -> list[tuple[int, str]]:
    """[(page_no, page_text)] — постранично (PDF) или одной страницей (txt/md/docx)."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        from pypdf import PdfReader

        return [(i + 1, page.extract_text() or "")
                for i, page in enumerate(PdfReader(str(path)).pages)]
    if suffix == ".docx":
        import docx

        return [(1, "\n".join(p.text for p in docx.Document(str(path)).paragraphs))]
    return [(1, path.read_text(encoding="utf-8"))]


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Символьные чанки с перекрытием — фолбэк для крупных секций без структуры."""
    chunks, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            for sep in ("\n", ". ", " "):
                cut = text.rfind(sep, start, end)
                if cut > start + size // 2:
                    end = cut + len(sep)
                    break
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        start = end - overlap if end < len(text) else end
    return chunks


def split_sections(pages_text: list[tuple[int, str]]) -> list[dict]:
    """Группирует строки в секции по заголовкам/пунктам.
    Возвращает [{"title": str|None, "lines": [(page, line)]}]."""
    sections = []
    cur_title = None
    cur_lines: list[tuple[int, str]] = []

    def flush():
        if cur_lines:
            sections.append({"title": cur_title, "lines": list(cur_lines)})

    for page, page_text in pages_text:
        for raw in page_text.splitlines():
            line = raw.rstrip()
            if not line.strip():
                continue
            if cur_lines and page != cur_lines[-1][0]:
                flush()  # смена страницы = граница чанка (точные страницы в sources[].page)
                cur_title, cur_lines = None, []
            if HEADER_RE.match(line) and cur_lines:
                flush()
                cur_title, cur_lines = None, []
            if cur_title is None and HEADER_RE.match(line):
                cur_title = line.strip()
            cur_lines.append((page, line))
    flush()
    return sections


def chunk_structured(pages_text: list[tuple[int, str]],
                     size: int = CHUNK_SIZE) -> list[dict]:
    """[{"text": str, "page": int, "section": str|None}].

    Секции (пункты/статьи с заголовками) пакуются в чанки <= size — пункт не рвётся
    посередине; секция крупнее size режется chunk_text с перекрытием.
    page = страница первой строки чанка.
    """
    chunks: list[dict] = []
    buf: list[tuple[int, str]] = []
    buf_len = 0

    def flush_buf():
        nonlocal buf, buf_len
        text = "\n".join(t for _p, t in buf).strip()
        if text:
            chunks.append({"text": text, "page": buf[0][0], "section": None})
        buf, buf_len = [], 0

    for sec in split_sections(pages_text):
        sec_text = "\n".join(t for _p, t in sec["lines"])
        sec_page = sec["lines"][0][0]
        if not sec_text:
            continue
        if buf and (buf_len + len(sec_text) + 1 > size or buf[-1][0] != sec_page):
            flush_buf()  # лимит размера или смена страницы -> новый чанк
        if len(sec_text) > size:
            flush_buf()
            for piece in chunk_text(sec_text, size, CHUNK_OVERLAP):
                chunks.append({"text": piece, "page": sec_page, "section": sec["title"]})
            continue
        buf.append((sec_page, sec_text))
        buf_len += len(sec_text) + 1
    flush_buf()
    return chunks


def chunk_text_spans(text: str, size: int, overlap: int) -> list[tuple[int, int]]:
    """[(start, end)] символьные границы чанков — та же логика разреза, что chunk_text."""
    spans = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            for sep in ("\n", ". ", " "):
                cut = text.rfind(sep, start, end)
                if cut > start + size // 2:
                    end = cut + len(sep)
                    break
        if text[start:end].strip():
            spans.append((start, end))
        start = end - overlap if end < len(text) else end
    return spans


def chunk_document_dense(pages_text, size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    """Плотные чанки по всему тексту (baseline-качество); page = страница начала чанка
    (чанк может пересекать границу страницы — тогда указана первая)."""
    parts, page_spans, offset = [], [], 0
    for page_no, ptext in pages_text:
        if parts and not ptext.startswith("\n"):
            parts.append("\n")
            offset += 1
        start = offset
        parts.append(ptext)
        offset += len(ptext)
        page_spans.append((page_no, start, offset))
    text = "".join(parts)

    def page_for(pos: int) -> int:
        for page, s, e in page_spans:
            if s <= pos < e:
                return page
        return page_spans[-1][0] if page_spans else 1

    return [{"text": text[s:e].strip(), "page": page_for(s), "section": None}
            for s, e in chunk_text_spans(text, size, overlap)]


def chunk_document_pages(pages_text, size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    """Чанки строго внутри страницы — sources[].page точны для каждого фрагмента."""
    chunks = []
    for page_no, ptext in pages_text:
        for s, e in chunk_text_spans(ptext, size, overlap):
            piece = ptext[s:e].strip()
            if piece:
                chunks.append({"text": piece, "page": page_no, "section": None})
    return chunks


def chunk_document(pages_text, size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    """Единая точка входа (CHUNKER env): dense | dense_pages | structured."""
    if CHUNKER_MODE == "structured":
        return chunk_structured(pages_text, size)
    if CHUNKER_MODE == "dense_pages":
        return chunk_document_pages(pages_text, size, overlap)
    return chunk_document_dense(pages_text, size, overlap)


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
                 chunks: list[dict], vectors) -> int:
    """Идемпотентно кладёт чанки одного документа в индекс.

    chunks: [{"text": str, "page": int}] (ключ "section" опционален).
    Перед записью удаляет прежние точки этого doc_id. Возвращает число чанков.
    """
    ensure_collection(client)
    doc_id = doc_id_for(filename)
    client.delete(COLLECTION, points_selector=FilterSelector(
        filter=Filter(must=[FieldCondition(key="doc_id",
                                           match=MatchValue(value=doc_id))])))
    client.upsert(COLLECTION, points=[
        PointStruct(id=point_id_for(filename, i), vector=v.tolist(),
                    payload={"doc_id": doc_id, "file": filename,
                             "text": c["text"], "page": c.get("page")})
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
        chunks = chunk_document(read_text_pages(f))
        if not chunks:
            print(f"  {f.name}: текста нет, пропущен")
            continue
        vectors = model.encode([c["text"] for c in chunks])
        index_chunks(client, filename=f.name, chunks=chunks, vectors=vectors)
        total += len(chunks)
        pages = sorted({c["page"] for c in chunks})
        print(f"  {f.name}: {len(chunks)} чанков (стр. {pages[0]}-{pages[-1]})")

    indexed = client.count(COLLECTION, exact=True).count
    print(f"Готово: {total} чанков записано, всего точек в '{COLLECTION}': {indexed}")


if __name__ == "__main__":
    main()
