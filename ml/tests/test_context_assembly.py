"""Тесты контекст-ассемблера: склейка overlap-чанков без потери контента."""

from submit.solution import assemble_context

OVER = "А" * 50  # ровно overlap чанкинга
C1 = {"file": "Договор X", "chunk_idx": 0, "text": "Пункт 4.1. Неустойка 0,1% за каждый день просрочки."}
C2 = {"file": "Договор X", "chunk_idx": 1, "text": OVER + " Пункт 4.2. Но не более 10% от стоимости."}
C3 = {"file": "Договор Y", "chunk_idx": 0, "text": "Статья 70. Испытание при приёме на работу."}


def test_overlap_deduplicated():
    ctx = assemble_context([(C2, 0.6), (C1, 0.55)], max_chars=4000)
    assert ctx.count(OVER) == 1, "дубликат overlap должен вырезаться"


def test_no_content_loss():
    top = [(C2, 0.6), (C1, 0.55), (C3, 0.5)]
    ctx = assemble_context(top, max_chars=4000)
    for c, _s in top:
        assert c["text"].strip() in ctx, "исходный чанк должен входить в контекст целиком"


def test_blocks_ordered_by_relevance():
    ctx = assemble_context([(C3, 0.4), (C1, 0.6)], max_chars=4000)
    assert ctx.index("Договор X") < ctx.index("Договор Y")


def test_cross_document_blocks_separate():
    ctx = assemble_context([(C1, 0.6), (C3, 0.5)], max_chars=4000)
    assert "Договор X" in ctx and "Статья 70" in ctx
    # разные документы не склеиваются в один блок: каждый со своим заголовком
    assert ctx.count("Документ:") == 2


def test_max_chars_respected():
    big = {"file": "Документ Z", "chunk_idx": 0, "text": "фрагмент " * 2000}
    ctx = assemble_context([(big, 0.9)], max_chars=1500)
    assert len(ctx) <= 1500


def test_numbering_present():
    ctx = assemble_context([(C1, 0.6), (C3, 0.5)], max_chars=4000)
    assert "[1] Документ: Договор X" in ctx
    assert "[2] Документ: Договор Y" in ctx


def test_empty_top_gives_empty():
    assert assemble_context([], max_chars=4000) == ""
