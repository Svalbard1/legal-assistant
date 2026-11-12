"""Собирает ZIP-сабмит для платформы: файлы в корне архива, без вложенной папки.

Запуск (из папки ml/submit/):  python build_zip.py
Результат: ../submission_ГГГГММДД_ЧЧММ.zip

По регламенту: solution.py — обязательная точка входа; requirements.txt — только
библиотеки из разрешённого набора с зафиксированными версиями; дополнительные
корневые .py-модули можно добавить в FILES (вложенные папки НЕ переносятся
платформой). База знаний и вопросы в ZIP не включаются — платформа кладёт их
в DATA_DIR сама. Лимит: 128 МБ.
"""

import zipfile
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
FILES = ["solution.py", "requirements.txt"]


def main():
    out = HERE.parent / f"submission_{datetime.now():%Y%m%d_%H%M}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in FILES:
            zf.write(HERE / name, arcname=name)
    size_mb = out.stat().st_size / 1024 / 1024
    print(f"OK: {out.name} ({size_mb:.2f} МБ)")
    if size_mb > 128:
        raise SystemExit("Превышен лимит 128 МБ!")


if __name__ == "__main__":
    main()
