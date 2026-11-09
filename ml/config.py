from pathlib import Path

ML_DIR = Path(__file__).resolve().parent
DATA_DIR = ML_DIR / "data" / "sample"       # корпус для CLI-индексации (ingest.py)
UPLOAD_DIR = ML_DIR / "data" / "uploads"    # файлы, пришедшие через POST /ingest
QDRANT_PATH = ML_DIR / ".qdrant"      # локальное хранилище (в гите нет)

EMBED_MODEL = "BAAI/bge-m3"           # 1024-мерные эмбеддинги
COLLECTION = "legal_docs"
CHUNK_SIZE = 500                      # символов на чанк
CHUNK_OVERLAP = 50
TOP_K = 3

QUERY_PREFIX = "Represent this sentence for searching relevant passages: "  # инструкция bge-m3 для поисковых запросов (даёт +recall, проверено eval)
