"""Тесты структурного чанкинга: секции по пунктам/заголовкам, страницы, упаковка."""

from ingest import chunk_structured, split_sections

DOC = [
    (1, "ДОГОВОР ПОСТАВКИ"),
    (1, ""),
    (1, "1. ПРЕДМЕТ ДОГОВОРА"),
    (1, "1.1. Поставщик обязуется поставить офисную мебель: кресла и столы."),
    (1, ""),
    (1, "2. ЦЕНА И ПОРЯДОК РАСЧЁТОВ"),
    (1, "2.1. Общая стоимость товара составляет 1 200 000 рублей, НДС не облагается."),
    (1, "2.2. Предоплата 40% в течение 5 рабочих дней после подписания."),
    (2, ""),
    (2, "3. ОТВЕТСТВЕННОСТЬ СТОРОН"),
    (2, "3.1. " + "Длинный пункт про неустойку и штрафы за просрочку. " * 40),
]


def test_sections_split_on_numbered_headers():
    sections = split_sections(DOC)
    titles = [s["title"] for s in sections]
    # заголовки-границы: "1. ПРЕДМЕТ", "2. ЦЕНА", "3. ОТВЕТСТВЕННОСТЬ"
    assert "1. ПРЕДМЕТ ДОГОВОРА" in titles
    assert "2. ЦЕНА И ПОРЯДОК РАСЧЁТОВ" in titles
    assert "3. ОТВЕТСТВЕННОСТЬ СТОРОН" in titles
    # преамбула до первого заголовка тоже секция
    assert sections[0]["lines"][0][1] == "ДОГОВОР ПОСТАВКИ"


def test_chunk_keeps_clause_together():
    chunks = chunk_structured(DOC, size=500)
    texts = [c["text"] for c in chunks]
    # пункт 2.1 и 2.2 (одна секция) не разорваны: вместе в одном чанке
    together = [t for t in texts if "1 200 000" in t and "Предоплата 40%" in t]
    assert together, "пункты одной секции должны попадать в один чанк"


def test_page_attribution():
    chunks = chunk_structured(DOC, size=500)
    # преамбула со страницы 1 открывает первый чанк
    assert any(c["page"] == 1 and c["text"].startswith("ДОГОВОР ПОСТАВКИ") for c in chunks)
    # 2.1 и 2.2 с одной страницы — в одном чанке (пункт не разорван)
    assert any(c["page"] == 1 and "1 200 000" in c["text"] and "Предоплата 40%" in c["text"]
               for c in chunks)
    # смена страницы = новый чанк: секция 3 целиком со страницы 2
    assert any(c["page"] == 2 and c["text"].startswith("3. ОТВЕТСТВЕННОСТЬ СТОРОН")
               for c in chunks)


def test_big_section_falls_back_to_char_split():
    chunks = chunk_structured(DOC, size=500)
    big = [c for c in chunks if "неустойку и штрафы" in c["text"]]
    assert len(big) >= 2, "крупная секция должна быть порезана на несколько чанков"
    assert all(len(c["text"]) <= 500 for c in big)


def test_every_chunk_has_page_and_text():
    for c in chunk_structured(DOC, size=500):
        assert isinstance(c["page"], int) and c["page"] >= 1
        assert c["text"].strip()


def test_plain_text_without_headers_still_chunked():
    plain = [(1, "слово " * 1500)]  # нет ни одного заголовка
    chunks = chunk_structured(plain, size=500)
    assert len(chunks) >= 3
    assert all(c["page"] == 1 for c in chunks)
