from pathlib import Path

ML_DIR = Path(__file__).resolve().parent
DATA_DIR = ML_DIR / "data" / "sample"       # корпус для CLI-индексации (ingest.py)
UPLOAD_DIR = ML_DIR / "data" / "uploads"    # файлы, пришедшие через POST /ingest
QDRANT_PATH = ML_DIR / ".qdrant"      # локальное хранилище (в гите нет)

EMBED_MODEL = "BAAI/bge-m3"           # 1024-мерные эмбеддинги
COLLECTION = "legal_docs"
CHUNK_SIZE = 400                      # символов на чанк (eval: recall@3 0.926 = baseline, MRR 0.865 > 0.844; на golden_kb recall@3 1.0)
CHUNK_OVERLAP = 50
TOP_K = 3

QUERY_PREFIX = ""  # bge-m3 не требует e5-инструкцию: без неё recall@1 +11 п.п., MRR +0.065 (eval_kb 14.11; подтверждено платформой: +1.7 балла)
