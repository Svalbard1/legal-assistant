"""Golden-QA оценка retrieval: recall@k, MRR, латентность.

Индекс должен быть собран заранее: python ingest.py
Запуск (из папки ml/):
    python eval.py                        # baseline текущего пайплайна
    python eval.py --json /tmp/eval_base.json
    python eval.py --query-prefix "Represent this sentence for searching relevant passages: "
    python eval.py --top-k 5

Так сравниваются изменения пайплайна (чанкинг, реранкер, префикс запроса):
сняли baseline -> внесли изменение -> повторили -> сравнили сводки.

Метрика «попадание» для вопроса: в топ-K найден чанк этого файла (если задан
expect_file), содержащий хотя бы одно ключевое слово из expect_contains_any
(без учёта регистра). Датасет: golden_qa.jsonl — вопросы по кейсу ПСБ и
тестовому договору; когда организаторы выдадут настоящую базу знаний,
расширяется только jsonl, код не меняется.
"""

import argparse
import json
import time
from pathlib import Path

from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

from config import COLLECTION, EMBED_MODEL, QDRANT_PATH, QUERY_PREFIX

HERE = Path(__file__).resolve().parent
GOLDEN_PATH = HERE / "golden_qa.jsonl"


def load_golden(path: Path = GOLDEN_PATH) -> list[dict]:
    items = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("//"):
                items.append(json.loads(line))
    return items


def first_hit_rank(hits, item: dict) -> int:
    """Ранг (с 1) первого чанка, отвечающего критерию попадания. 0 = попадания нет."""
    want_file = item.get("expect_file")
    keys = [k.lower() for k in item.get("expect_contains_any", [])]
    for rank, hit in enumerate(hits, 1):
        if want_file and hit.payload.get("file") != want_file:
            continue
        text = (hit.payload.get("text") or "").lower()
        if not keys or any(k in text for k in keys):
            return rank
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description="Golden-QA оценка retrieval")
    ap.add_argument("--top-k", type=int, default=10, help="глубина поиска (по умолчанию 10)")
    ap.add_argument("--query-prefix", default=QUERY_PREFIX,
                    help="префикс запроса для A/B (например, инструкция bge-m3)")
    ap.add_argument("--json", dest="json_out", help="сохранить сводку в JSON-файл")
    args = ap.parse_args()

    items = load_golden()
    print(f"Golden-QA: {len(items)} вопросов | top_k={args.top_k} | "
          f"prefix={'да' if args.query_prefix else 'нет'}")

    print(f"Загружаю {EMBED_MODEL} (первый запуск ~20-40 с)...")
    model = SentenceTransformer(EMBED_MODEL)
    client = QdrantClient(path=str(QDRANT_PATH))
    if not client.collection_exists(COLLECTION):
        raise SystemExit("Индекс пуст — сначала выполни: python ingest.py")

    ks = tuple(k for k in (1, 3, 5, 10) if k <= args.top_k)
    hits_at = {k: 0 for k in ks}
    rr_total, latencies = 0.0, []
    misses = []

    for item in items:
        query = args.query_prefix + item["question"]
        t0 = time.monotonic()
        vec = model.encode(query).tolist()
        hits = client.query_points(COLLECTION, query=vec, limit=args.top_k).points
        lat_ms = (time.monotonic() - t0) * 1000
        latencies.append(lat_ms)

        rank = first_hit_rank(hits, item)
        if rank:
            rr_total += 1.0 / rank
            for k in ks:
                if rank <= k:
                    hits_at[k] += 1
        else:
            misses.append(item["id"])

        top1 = round(hits[0].score, 3) if hits else 0.0
        status = f"rank={rank}" if rank else "MISS"
        print(f"  [{item['id']}] {status:<8} top1={top1:<7} {lat_ms:6.0f} мс   {item['question'][:64]}")

    n = len(items)
    summary = {
        "questions": n,
        "top_k": args.top_k,
        "query_prefix": args.query_prefix,
        "model": EMBED_MODEL,
    }
    print("\n=== ИТОГИ ===")
    for k in ks:
        recall = hits_at[k] / n
        summary[f"recall@{k}"] = round(recall, 3)
        print(f"  recall@{k:<2} = {hits_at[k]:>2}/{n} = {recall:.1%}")
    summary["mrr"] = round(rr_total / n, 3)
    summary["latency_ms_avg"] = round(sum(latencies) / n)
    summary["latency_ms_max"] = round(max(latencies))
    summary["misses"] = misses
    print(f"  MRR        = {summary['mrr']:.3f}")
    print(f"  Латентность: средняя {summary['latency_ms_avg']} мс / макс {summary['latency_ms_max']} мс")
    if misses:
        print(f"  Промахи: {', '.join(misses)}")
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Сводка сохранена: {args.json_out}")


if __name__ == "__main__":
    main()
