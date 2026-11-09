"""Юнит-тесты чанкинга: чистая логика, без модели и Qdrant."""

from ingest import chunk_text


def test_empty_text():
    assert chunk_text("") == []


def test_whitespace_only():
    assert chunk_text("   \n\t ") == []


def test_short_text_single_chunk():
    text = "Короткий договор. Один абзац."
    assert chunk_text(text) == [text]


def test_long_text_chunk_size_respected():
    text = "Юридический текст про неустойку и штрафы. " * 400  # ~17k символов
    chunks = chunk_text(text, size=500, overlap=50)
    assert len(chunks) > 10
    assert all(len(c) <= 500 for c in chunks)
    assert all(c.strip() for c in chunks)


def test_no_infinite_loop_on_solid_text():
    # текст без \n, ". " и пробелов — вынужденный жёсткий разрез
    chunks = chunk_text("а" * 2000, size=500, overlap=50)
    assert 4 <= len(chunks) <= 6
    assert all(c for c in chunks)


def test_no_content_loss():
    # каждое слово исходного текста должно попасть хотя бы в один чанк
    text = " ".join(f"слово{i:03d}" for i in range(200))
    joined = "\n".join(chunk_text(text, size=500, overlap=50))
    for i in range(0, 200, 13):
        assert f"слово{i:03d}" in joined


def test_chunks_have_overlap():
    text = " ".join(f"предложение номер {i} про поставку товара. " for i in range(60))
    chunks = chunk_text(text, size=500, overlap=50)
    assert len(chunks) >= 2
    # соседние чанки пересекаются: начало следующего встречается в предыдущем
    assert chunks[1][:20].strip() in chunks[0]
