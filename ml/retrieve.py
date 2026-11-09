"""Поиск по проиндексированным документам.

Запуск из папки ml/:  python retrieve.py "твой вопрос"
"""
import sys

from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

from config import COLLECTION, EMBED_MODEL, QDRANT_PATH, QUERY_PREFIX, TOP_K


def main() -> None:
    if len(sys.argv) < 2:
        print('Укажи запрос: python retrieve.py "вопрос"')
        return
    query = " ".join(sys.argv[1:])

    model = SentenceTransformer(EMBED_MODEL)
    client = QdrantClient(path=str(QDRANT_PATH))

    vec = model.encode(QUERY_PREFIX + query).tolist()
    hits = client.query_points(COLLECTION, query=vec, limit=TOP_K).points

    print(f"\nТоп-{TOP_K} для: {query}\n")
    for i, hit in enumerate(hits, 1):
        print(f"[{i}] {hit.payload['file']} (score={hit.score:.3f})")
        print(f"    {hit.payload['text'][:300]}...\n")


if __name__ == "__main__":
    main()