"""Тесты режимов чанкера: dense (baseline), dense_pages (точные страницы)."""

from ingest import chunk_document, chunk_document_dense, chunk_document_pages

PAGES = [
    (1, "ДОГОВОР ПОСТАВКИ. 1. ПРЕДМЕТ. Поставщик обязуется поставить мебель. " * 5),
    (2, "2. ОТВЕТСТВЕННОСТЬ. За просрочку неустойка 0,1% за каждый день. " * 5),
]


def test_dense_returns_chunks_with_page_of_start():
    chunks = chunk_document_dense(PAGES, size=300, overlap=30)
    assert len(chunks) >= 2
    assert all(c["text"].strip() for c in chunks)
    assert all(isinstance(c["page"], int) for c in chunks)


def test_dense_pages_exact_page_attribution():
    chunks = chunk_document_pages(PAGES, size=300, overlap=30)
    assert all(c["page"] in (1, 2) for c in chunks)
    # фрагменты про ответственность — только со страницы 2
    for c in chunks:
        if "неустойка 0,1%" in c["text"]:
            assert c["page"] == 2
    # фрагменты про поставку мебели — только со страницы 1
    for c in chunks:
        if "поставить мебель" in c["text"]:
            assert c["page"] == 1


def test_chunk_document_dispatch_default_dense_pages():
    chunks = chunk_document(PAGES, size=300, overlap=30)
    assert chunks and all(set(c) >= {"text", "page", "section"} for c in chunks)


def test_structured_mode_still_available():
    chunks = chunk_document.__globals__["chunk_structured"](PAGES)
    assert chunks
