# ML-сервис: поиск по документам (RAG)

## Локальный запуск (5 минут)

```bash
cd ml

# Свой venv (вариант А). Первый install качает torch (~200 МБ CPU);
# чтобы точно взять CPU-сборку: pip install torch --index-url https://download.pytorch.org/whl/cpu
python3 -m venv venv && source venv/bin/activate
# (вариант Б — conda base, если пакеты уже установлены там)

pip install -r requirements.txt

python ingest.py                     # индексация ml/data/sample/ (идемпотентно: повтор = обновление, не дубликаты)
python retrieve.py "какая неустойка за просрочку поставки"  # CLI-поиск для отладки
uvicorn service:app --port 8001      # HTTP; Swagger: http://localhost:8001/docs
```

ВАЖНО: ровно один процесс (`uvicorn` без `--workers`) — локальный Qdrant держит файл блокировкой.

## Проверка

```bash
curl localhost:8001/health
curl -F "file=@data/sample/пример.txt" localhost:8001/ingest
curl -X POST localhost:8001/ask -H "Content-Type: application/json" \
     -d '{"question": "какая неустойка за просрочку поставки"}'
```

## Тесты

```bash
pip install -r requirements-dev.txt
python -m pytest tests -q            # ~10 с: API-смоук на фейковом энкодере, bge-m3 не грузится
```

## Оценка качества retrieval (golden-QA)

```bash
python ingest.py                     # индекс должен быть актуален
python eval.py                       # recall@1/3/5/10, MRR, латентность на 27 вопросах
python eval.py --json /tmp/base.json # сохранить сводку, чтобы сравнивать «до/после»
```

Датасет — `golden_qa.jsonl` (кейс ПСБ + тестовый договор). Расширяется без изменения кода.
Baseline (2026-11-09, с префиксом запроса): recall@3 = 92.6%, recall@10 = 100%, MRR = 0.844.
Любое изменение чанкинга/поиска/реранкера проверяем так: baseline -> изменение -> eval -> сравнение.

## Структура

| Файл | Что |
|---|---|
| `service.py` | FastAPI: `/health`, `/ingest`, `/ask` — точка стыковки с бекендом |
| `ingest.py` | парсинг → чанкинг → индексация (`index_chunks` общий для CLI и сервиса) |
| `retrieve.py` | CLI-поиск, удобно для отладки без HTTP |
| `config.py` | пути, модель, размер чанков |
| `docs/` | контракт API v0.1 и гайды интеграции (источник истины по стыку) |
| `tests/` | юнит + smoke (API на фейковом энкодере) |
| `data/sample/` | тестовый корпус (в git: `пример.txt`; PDF/DOCX — нет) |
| `data/uploads/` | файлы, пришедшие через `POST /ingest` (в git не попадают) |

## Переменные окружения

См. `.env.example`: `LLM_API_URL` — адрес vLLM; пусто → `llm: "stub"` в ответах.

## Документы

- Контракт API: [docs/API_CONTRACT.md](docs/API_CONTRACT.md) — менять только вместе с `service.py`, через PR.
- Гайд интеграции для бекенда: [docs/BACKEND_INTEGRATION.md](docs/BACKEND_INTEGRATION.md).

## Известные ограничения v0.1

- Генерация — заглушка (выжимка источников); настоящий LLM появится с vLLM.
- `/ingest` синхронный (большой PDF — десятки секунд); async — v0.2.
- Дедупликация по имени файла: заливка файла с тем же именем обновляет документ;
  один документ под разными именами = разные `doc_id` (по хэшу содержимого — v0.2).
- Индекс и uploads живут в volume; без volume рестарт контейнера = индекс с нуля.
