"""Эксперимент: гибридный поиск dense + BM25 (RRF-фьюжн) против чистого dense.

Гипотеза: юридические запросы с точными ссылками ("п. 4.1", "ст. 70", "А-08/2024")
BM25 ловит лучше эмбеддингов; RRF (Reciprocal Rank Fusion, k=60) объединяет.

Корпуса и эталоны:
  1. Кейс ПСБ: ml/data/sample/* + golden_qa.jsonl (27 вопросов)
  2. База организаторов: knowledge-base.zip + demo_questions.csv + golden_kb.jsonl (18)

Режимы: dense (базлайн) | bm25 | rrf.

Запуск (из папки ml/):
    python eval_hybrid.py
    python eval_hybrid.py --json /tmp/hybrid.json
"""

import argparse
import json
import math
import re
import time
from collections import Counter
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

from config import EMBED_MODEL, QUERY_PREFIX
from eval_kb import load_golden as load_golden_kb
from eval_kb import chunk_text, load_kb, load_questions
from ingest import chunk_document, read_text_pages

HERE = Path(__file__).resolve().parent


def _tokenize(text: str):
    return re.findall(r"\w+", text.lower().replace("ё", "е"))


class BM25Index:
    """Компактный BM25 (k1=1.5, b=0.75) — как в solution.py."""

    def __init__(self, texts):
        self.docs = [_tokenize(t) for t in texts]
        self.len = [len(d) or 1 for d in self.docs]
        self.avg = sum(self.len) / len(self.len) if self.len else 1.0
        self.k1, self.b = 1.5, 0.75
        self.df = Counter()
        for d in self.docs:
            self.df.update(set(d))
        self.N = len(texts)

    def search(self, query, top_k):
        q = _tokenize(query)
        out = []
        for i in range(self.N):
            counts = Counter(self.docs[i])
            score = 0.0
            for t in q:
                if t not in counts:
                    continue
                idf = math.log((self.N - self.df[t] + 0.5) / (self.df[t] + 0.5) + 1.0)
                tf = counts[t]
                score += idf * (tf * (self.k1 + 1)) / (
                    tf + self.k1 * (1 - self.b + self.b * self.len[i] / self.avg))
            out.append((score, i))
        out.sort(reverse=True)
        return out[:top_k]


def rrf_fuse(rank_lists, k=60):
    """{index: rrf_score} по спискам рангов (rank с 0)."""
    fused = {}
    for ranks in rank_lists:
        for pos, idx in enumerate(ranks):
            fused[idx] = fused.get(idx, 0.0) + 1.0 / (k + pos + 1)
    return fused


def load_case_corpus():
    chunks = []
    sample = HERE / "data" / "sample"
    for f in sorted(sample.iterdir()):
        if f.suffix.lower() not in {".pdf", ".docx", ".txt", ".md"}:
            continue
        for c in chunk_document(read_text_pages(f)):
            chunks.append({"file": f.name, "text": c["text"], "page": c["page"]})
    golden = [json.loads(l) for l in
              (HERE / "golden_qa.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    questions = [(g["id"], g["question"]) for g in golden]
    return chunks, questions, golden, "кейс ПСБ"


def load_kb_corpus():
    kb_zip = HERE / "data" / "kb" / "knowledge-base.zip"
    docs = load_kb(kb_zip)
    chunks = []
    for fname, text in docs:
        for piece in chunk_text(text):
            chunks.append({"file": fname, "text": piece, "page": 1})
    questions = load_questions(HERE / "data" / "kb" / "demo_questions.csv")
    golden = {g["id"]: g for g in load_golden_kb(HERE / "golden_kb.jsonl")}
    # единый вид: refuse-вопрос помечаем и исключаем из recall
    golden_list = []
    for qid, q in questions:
        g = golden.get(qid, {"type": "hit", "expect_doc_any": []})
        golden_list.append({"id": qid, "question": q, **g})
    return chunks, questions, golden_list, "база организаторов"


def evaluate(chunks, questions, golden, dense_M, bm25, mode, top_k=5):
    """recall@1/3/5 + MRR на hit-вопросах; refusal — отдельно (score для калибровки)."""
    hits_at = {1: 0, 3: 0, 5: 0}
    rr, refusal_scores, misses = 0.0, [], []
    n_hit = 0
    for q_index, (qid, question) in enumerate(questions):
        g = golden[q_index]
        if g.get("type") == "refusal":
            if mode == "dense":  # считаем один раз, только для калибровки
                best = float(np.max(dense_M[q_index]))
                refusal_scores.append(best)
            continue
        expect = [k.lower() for k in             g.get("expect_doc_any", g.get("expect_contains_any", []))]
        expect_file = g.get("expect_file", "").lower()

        if mode == "dense":
            ranked = np.argsort(-dense_M[q_index])[:top_k]
            top = [(chunks[i], float(dense_M[q_index][i])) for i in ranked]
        elif mode == "bm25":
            out = bm25.search(question, top_k)
            top = [(chunks[i], s) for s, i in out]
        else:  # rrf
            dense_order = list(np.argsort(-dense_M[q_index])[:top_k * 2])
            bm25_order = [i for _s, i in bm25.search(question, top_k * 2)]
            fused = rrf_fuse([dense_order, bm25_order])
            best = sorted(fused.items(), key=lambda kv: -kv[1])[:top_k]
            top = [(chunks[i], s) for i, s in best]

        n_hit += 1
        rank = 0
        for r, (c, _s) in enumerate(top, 1):
            fl = c["file"].lower()
            if expect_file and expect_file not in fl:
                continue
            if any(k in fl or k in c["text"].lower() for k in expect):
                rank = r
                break
        if rank:
            rr += 1.0 / rank
            for k in (1, 3, 5):
                if rank <= k:
                    hits_at[k] += 1
        else:
            misses.append(qid)
    return {"hits_at": hits_at, "mrr": rr / n_hit if n_hit else 0,
            "misses": misses, "refusal_scores": refusal_scores}


def main():
    ap = argparse.ArgumentParser(description="Гибрид dense+BM25 (RRF) — эксперимент")
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--json", dest="json_out")
    args = ap.parse_args()

    print(f"Загружаю {EMBED_MODEL}...")
    model = SentenceTransformer(EMBED_MODEL)
    results = {}

    for loader in (load_case_corpus, load_kb_corpus):
        chunks, questions, golden, label = loader()
        print(f"\n========== КОРПУС: {label} | чанков: {len(chunks)} | "
              f"вопросов: {len(questions)} ==========")

        t0 = time.monotonic()
        dense_M = np.asarray(model.encode(
            [QUERY_PREFIX + q for _, q in questions],
            normalize_embeddings=True, show_progress_bar=False)) @ np.asarray(
            model.encode([c["text"] for c in chunks],
                         normalize_embeddings=True, show_progress_bar=False)).T
        print(f"[embed] матрица {dense_M.shape} за {time.monotonic() - t0:.0f} с")
        bm25 = BM25Index([c["text"] for c in chunks])

        corpus_res = {}
        for mode in ("dense", "bm25", "rrf"):
            r = evaluate(chunks, questions, golden, dense_M, bm25, mode, args.top_k)
            recall = {f"recall@{k}": round(r["hits_at"][k] /
                      max(1, sum(1 for g in golden if g.get("type") != "refusal")), 3)
                      for k in (1, 3, 5)}
            corpus_res[mode] = {"recall": recall, "mrr": round(r["mrr"], 3),
                                "misses": r["misses"]}
            print(f"  [{mode:<5}] " + " | ".join(
                f"recall@{k}={recall[f'recall@{k}']:.1%}" for k in (1, 3, 5))
                + f" | MRR={r['mrr']:.3f}" + (f" | промахи: {r['misses']}" if r["misses"] else ""))
            if r["refusal_scores"]:
                print(f"           ловушка top1 (dense): {[round(x, 3) for x in r['refusal_scores']]}")
        results[label] = corpus_res

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nСводка сохранена: {args.json_out}")


if __name__ == "__main__":
    main()
