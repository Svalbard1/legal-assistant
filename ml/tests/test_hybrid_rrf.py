"""Тесты RRF-фьюжна гибридного поиска (dense + BM25)."""

from submit.solution import rrf_fuse


def test_rrf_merges_two_rankings():
    fused = rrf_fuse([[0, 1, 2], [2, 1, 0]])
    # doc 1: второе место в обоих; doc 0: первое в A, последнее в B; doc 2 наоборот
    assert fused[1] > fused[0] and fused[1] > fused[2]


def test_rrf_missing_doc_gets_nothing():
    fused = rrf_fuse([[0, 1], [5, 6]])
    assert fused[0] > 0 and fused[5] > 0
    assert 3 not in fused


def test_rrf_ordering_deterministic():
    a = rrf_fuse([[0, 1, 2, 3], [3, 2, 1, 0]])
    b = rrf_fuse([[0, 1, 2, 3], [3, 2, 1, 0]])
    assert a == b
