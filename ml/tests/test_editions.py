"""Тесты companion-edition expansion (правило «дата события -> редакция»)."""

from submit.solution import doc_base, expand_editions

R25 = {"file": "Регламент согласования договоров ред 2025", "text": "порог 15 млн, п. 1.3"}
R23 = {"file": "Регламент согласования договоров ред 2023 (утратил силу)", "text": "порог 10 млн, п. 2.4"}
DOG = {"file": "Договор аренды А-08-2024", "text": "аренда"}


def test_doc_base_unifies_editions():
    assert doc_base(R23["file"]) == doc_base(R25["file"])
    assert doc_base(R23["file"]) == "Регламент согласования договоров"


def test_companion_lifted_into_context():
    # ред 2023 нашлась поиском ниже головы контекста (ранг 4 при top-8)
    search = [(R25, 0.54), (DOG, 0.53), (DOG, 0.52), (R23, 0.45)]
    out = expand_editions(search, context_k=3, extra=2)
    files = [c["file"] for c, _s in out[:4]]
    assert R23["file"] in files, "компаньон-редакция должен попасть в контекст"
    assert files[3] == R23["file"]  # компаньон стоит сразу после головы


def test_no_duplicates_and_cap():
    search = [(R25, 0.6), (R23, 0.55), (R25, 0.5), (R23, 0.45)]
    out = expand_editions(search, context_k=1, extra=2)
    files = [c["file"] for c, _s in out]
    assert files.count(R25["file"]) == 1
    assert files.count(R23["file"]) == 1


def test_head_unchanged_for_threshold():
    search = [(DOG, 0.51), (R25, 0.5), (R23, 0.49)]
    out = expand_editions(search, context_k=3, extra=2)
    assert out[0] == search[0], "порог отказа считается по неизменной голове"
