from pathlib import Path

ML_DIR = Path(__file__).resolve().parent
DATA_DIR = ML_DIR / "data" / "sample"
QDRANT_PATH = ML_DIR / ".qdrant"      # локальное хранилище, в git не попадёт

EMBED_MODEL = "BAAI/bge-m3"           # 1024-мерные эмбеддинги
COLLECTION = "legal_docs"
CHUNK_SIZE = 500                      # символов на чанк
CHUNK_OVERLAP = 50
TOP_K = 3