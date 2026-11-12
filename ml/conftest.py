"""Pytest: добавляет ml/ в sys.path, чтобы тесты импортировали config/ingest/service."""

import sys
from pathlib import Path

ML_DIR = Path(__file__).resolve().parent
if str(ML_DIR) not in sys.path:
    sys.path.insert(0, str(ML_DIR))
