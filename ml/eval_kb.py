"""Golden-QA на реальной базе знаний организаторов (см. ml/data/kb/).

Вопросы — data/kb/demo_questions.csv (18 шт. от организаторов, включая 5 диалогов).
Ожидания — golden_kb.jsonl: ожидаемый документ (из эталонных ответов demo_output.csv)
и тип вопроса: hit (ответ есть в базе) | refusal (обоснованный отказ — документов нет).

Главная ценность: калибровка REFUSAL_THRESHOLD — на «ловушечных» вопросах (ответа в
базе нет) замеряется лучший косинусный score. Если он сопоставим с релевантными,
порог по score отказ не поймает — и отказ остаётся задачей LLM + анализа вопроса.

Чанкинг/эмбеддинги — те же, что в solution.py (chunk_text 500/50, bge-m3 + QUERY_PREFIX).

Запуск (из папки ml/):
    python eval_kb.py
    python eval_kb.py --json /tmp/eval_kb.json
    python eval_kb.py --top-k 5
"""

import argparse
import csv
import io
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

from config import EMBED_MODEL, QUERY_PREFIX

HERE = Path(__file__).resolve().parent
DOCX_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _docx_text(raw: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(raw)) as doc:
        xml = doc.read("word/document.xml")
    root = ET.fromstring(xml)
    return "\n".join(
        "".join(node.text or "" for node in p.iter(DOCX_NS + "t"))
        for p in root.iter(DOCX_NS + "p")
    )


def clean_doc_name(filename: str) -> str:
    """'документы компании__Договор аренды А-08-2024.txt' -> 'Договор аренды А-08-2024'."""
    name = re.sub(r"\.(txt|md|pdf|docx)$", "", filename, flags=re.IGNORECASE)
    name = re.sub(r"^(документы компании|законы)__\s*", "", name)
    return name.strip()


def load_kb(zip_path: Path):
    """[(clean_name, text)] — тексты документов из knowledge-base.zip."""
    docs = []
    with zipfile.ZipFile(zip_path) as zf:
        for name in sorted(zf.namelist()):
            if name.endswith("/") or "__MACOSX" in name:
                continue
            suffix = Path(name).suffix.lower()
            raw = zf.read(name)
            try:
                if suffix == ".docx":
                    text = _docx_text(raw)
                elif suffix in (".txt", ".md"):
                    text = raw.decode("utf-8-sig")
                elif suffix == ".pdf":
                    try:
                        from pypdf import PdfReader
                        text = "\n".join((p.extract_text() or "")
                                         for p in PdfReader(io.BytesIO(raw)).pages)
                    except ImportError:
                        continue
                else:
                    continue
            except (UnicodeDecodeError, KeyError, ValueError, zipfile.BadZipFile) as exc:
                print(f"[kb] {name}: {exc}", file=sys.stderr)
                continue
            text = re.sub(r"\s+", " ", text).strip()
            if text:
                docs.append((clean_doc_name(name), text))
    return docs


def load_questions(path: Path):
    """[(id, question)] из questions.csv организаторов."""
    rows = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            qid = (row.get("id") or "").strip()
            question = (row.get("question") or "").strip()
            if qid and question:
                rows.append((qid, question))
    return rows


def load_golden(path: Path):
    return [json.loads(line) for line in
            path.read_text(encoding="utf-8").splitlines() if line.strip()]


def chunk_text(text: str, size: int = 500, overlap: int = 50):
    """Тот же чанкинг, что в solution.py (500/50, разрез по предложениям)."""
    chunks, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            for sep in ("\n", ". ", " "):
                cut = text.rfind(sep, start, end)
                if cut > start + size // 2:
                    end = cut + len(sep)
                    break
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        start = end - overlap if end < len(text) else end
    return chunks


EDITION_MARK_RE = re.compile(r"\s*\(утратил силу\)|\s*ред\.?\s*\d{4}", re.IGNORECASE)


def doc_base(name: str) -> str:
    """'Регламент ... ред 2023 (утратил силу)' и '... ред 2025' -> один базовый титул."""
    return EDITION_MARK_RE.sub("", name).strip(" ,;-")


def expand_editions(top, context_k=3, extra=2):
    """Поднимает в контекст чанки других редакций документов из топ-context_k.

    LLM с правилом «дата события -> редакция» сам выберет применимую версию;
    retrieval лишь гарантирует, что обе редакции попали в контекст."""
    head = list(top[:context_k])
    tail = list(top[context_k:])
    bases = {doc_base(c["file"]) for c, _s in head}
    head_files = {c["file"] for c, _s in head}
    companions, rest = [], []
    for c, s in tail:
        if len(companions) < extra and doc_base(c["file"]) in bases \
                and c["file"] not in head_files:
            companions.append((c, s))
        else:
            rest.append((c, s))
    return head + companions + rest


def main():
    ap = argparse.ArgumentParser(description="Golden-QA на реальной базе организаторов")
    ap.add_argument("--zip", default="data/kb/knowledge-base.zip")
    ap.add_argument("--questions", default="data/kb/demo_questions.csv")
    ap.add_argument("--golden", default="golden_kb.jsonl")
    ap.add_argument("--top-k", type=int, default=8)  # глубина поиска
    ap.add_argument("--context-k", type=int, default=3)  # размер головы контекста
    ap.add_argument("--companion-extra", type=int, default=2)  # максимум чанков-компаньонов
    ap.add_argument("--no-expand", action="store_true")  # отключить расширение редакций
    ap.add_argument("--json", dest="json_out")
    args = ap.parse_args()

    questions = load_questions(Path(args.questions))
    golden = {g["id"]: g for g in load_golden(Path(args.golden))}
    print(f"База: {Path(args.zip).name} | вопросов: {len(questions)} | top_k={args.top_k}")

    print(f"Загружаю {EMBED_MODEL}...")
    from ingest import chunk_text  # тот же чанкинг, что в solution.py

    model = SentenceTransformer(EMBED_MODEL)
    chunks = []
    for fname, text in load_kb(Path(args.zip)):
        for piece in chunk_text(text):
            chunks.append({"file": fname, "text": piece})
    print(f"[index] чанков: {len(chunks)}", file=sys.stderr)
    if not chunks:
        raise SystemExit("База пуста — проверь путь к knowledge-base.zip")

    t0 = time.monotonic()
    chunk_vecs = model.encode([c["text"] for c in chunks],
                              normalize_embeddings=True, show_progress_bar=False)
    query_vecs = model.encode([QUERY_PREFIX + q for _, q in questions],
                              normalize_embeddings=True, show_progress_bar=False)
    print(f"[embed] {len(chunks)} чанков + {len(questions)} запросов "
          f"за {time.monotonic() - t0:.0f} с", file=sys.stderr)

    M = np.asarray(chunk_vecs)
    ks = (1, 3) if args.top_k >= 3 else (1,)
    hits_at = {k: 0 for k in ks}
    rr_total = 0.0
    hit_scores, refusal_scores, edition_rows, misses = [], [], [], []

    for q_index, (qid, question) in enumerate(questions):
        g = golden.get(qid, {"type": "hit", "expect_doc_any": []})
        scores = M @ np.asarray(query_vecs[q_index])
        order = np.argsort(-scores)[:args.top_k]
        top = [(chunks[i], float(scores[i])) for i in order]
        strict = top[:3]
        if args.no_expand:
            final = top[:args.context_k]
        else:
            final = expand_editions(top, args.context_k, args.companion_extra)

        expect = [k.lower() for k in g.get("expect_doc_any", [])]
        rank, rank_strict = 0, 0
        for r, (c, _s) in enumerate(final, 1):
            fname_l = c["file"].lower()
            if any(k in fname_l for k in expect):
                rank = r
                break
        for r, (c, _s) in enumerate(strict, 1):
            fname_l = c["file"].lower()
            if any(k in fname_l for k in expect):
                rank_strict = r
                break
        best = top[0][1] if top else 0.0

        if g["type"] == "refusal":
            refusal_scores.append(best)
            print(f"  [{qid}] refusal-cand  top1={best:.3f}  {question[:56]}")
        else:
            hit_scores.append(best)
            if rank:
                rr_total += 1.0 / rank
                for k in ks:
                    if rank <= k:
                        hits_at[k] += 1
            else:
                misses.append(qid)
            status = f"rank={rank} (strict {rank_strict})" if rank else "MISS"
            print(f"  [{qid}] {status:<8} top1={best:.3f}  {question[:56]}")

        if any("ред 2025" in k or "ред 2023" in k for k in expect):
            r25 = next((r for r, (c, _s) in enumerate(final, 1)
                        if "ред 2025" in c["file"].lower()), None)
            r23 = next((r for r, (c, _s) in enumerate(final, 1)
                        if "ред 2023" in c["file"].lower()), None)
            edition_rows.append({"id": qid, "rank_red2025": r25, "rank_red2023": r23})
            print(f"      редакции: ред 2025 rank={r25}, ред 2023 rank={r23}")

    n_hit = len(hit_scores)
    summary = {"questions": len(questions), "top_k": args.top_k,
               "context_k": args.context_k, "expand": not args.no_expand,
               "model": EMBED_MODEL, "chunks": len(chunks)}
    print("\n=== ИТОГИ (hit-вопросы) ===")
    for k in ks:
        recall = hits_at[k] / n_hit if n_hit else 0.0
        summary[f"recall@{k}"] = round(recall, 3)
        print(f"  recall@{k} (контекст {args.context_k}+компаньоны) = {hits_at[k]}/{n_hit} = {recall:.1%}")
    summary["mrr"] = round(rr_total / n_hit, 3) if n_hit else 0.0
    print(f"  MRR = {summary['mrr']:.3f}")
    if misses:
        summary["misses"] = misses
        print(f"  Промахи: {', '.join(misses)}")

    if refusal_scores:
        print(f"\n=== КАЛИБРОВКА REFUSAL_THRESHOLD (ловушек: {len(refusal_scores)}) ===")
        print(f"  топ-1 score на ловушках: {[round(x, 3) for x in refusal_scores]}")
        print(f"  диапазон hit-вопросов: min={min(hit_scores):.3f} max={max(hit_scores):.3f}")
        summary["refusal_top1"] = [round(x, 3) for x in refusal_scores]
        summary["hit_top1_min"] = round(min(hit_scores), 3)
        for t in (0.35, 0.40, 0.45, 0.50, 0.55):
            caught = sum(1 for x in refusal_scores if x < t) / len(refusal_scores)
            lost = sum(1 for x in hit_scores if x < t) / len(hit_scores)
            summary[f"T={t}"] = {"refusal_caught": round(caught, 2),
                                 "false_refusal": round(lost, 2)}
            print(f"  T={t:.2f}: отказ пойман {caught:.0%} | ложных отказов {lost:.0%}")

    if edition_rows:
        print("=== РЕДАКЦИИ РЕГЛАМЕНТА (ранг ред 2025 / ред 2023) ===")
        summary["editions"] = edition_rows
        for row in edition_rows:
            print(f"  [{row['id']}] ред 2025: {row['rank_red2025']} | ред 2023: {row['rank_red2023']}")

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Сводка сохранена: {args.json_out}")


if __name__ == "__main__":
    main()
