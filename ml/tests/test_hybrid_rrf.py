"""Тесты RRF-фьюжна гибридного поиска (dense + BM25)."""

import pytest

from submit.solution import rrf_fuse


def test_rrf_merges_two_rankings():
    fused = rrf_fuse([[0, 1, 2], [2, 1, 0]])
    # Взаимодополняющие топы (0 в A + 2 в B) обгоняют «середняка» (1 в обоих списках)
    assert fused[0] == pytest.approx(fused[2])
    assert fused[0] > fused[1]


def test_rrf_missing_doc_gets_nothing():
    fused = rrf_fuse([[0, 1], [5, 6]])
    assert fused[0] > 0 and fused[5] > 0
    assert 3 not in fused


def test_rrf_ordering_deterministic():
    a = rrf_fuse([[0, 1, 2, 3], [3, 2, 1, 0]])
    b = rrf_fuse([[0, 1, 2, 3], [3, 2, 1, 0]])
    assert a == b
