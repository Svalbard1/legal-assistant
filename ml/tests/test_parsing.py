"""Юнит-тесты извлечения текста (лёгкие: только txt/md)."""

import pytest

from config import DATA_DIR
from ingest import read_text


def test_read_txt_from_sample_corpus():
    p = DATA_DIR / "пример.txt"
    assert p.exists(), "тестовый файл пример.txt должен быть в репо"
    text = read_text(p)
    assert "неустойку" in text
    assert "Арбитражный суд города Москвы" in text


def test_read_md(tmp_path):
    p = tmp_path / "note.md"
    p.write_text("# Заголовок\n\nТекст соглашения.", encoding="utf-8")
    assert "Заголовок" in read_text(p)


def test_unreadable_encoding_raises(tmp_path):
    # битая utf-8 последовательность: read_text не должен молчать
    p = tmp_path / "bad.txt"
    p.write_bytes(b"\xff\xfe broken \x00")
    with pytest.raises(UnicodeDecodeError):
        read_text(p)
