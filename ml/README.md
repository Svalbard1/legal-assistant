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

### Eval на реальной базе организаторов (eval_kb.py)

```bash
python eval_kb.py --json /tmp/eval_kb.json
```

18 demo-вопросов организаторов (включая диалоги и ловушку без ответа) на базе 21 документа.
Baseline (2026-11-10, dense 500/50 + префикс): recall@3 = 94.1%, MRR = 0.858 (hit-вопросы).
Отдельно: калибровка REFUSAL_THRESHOLD (ловушка 0.494 vs hit-min 0.516 — порог-пол 0.30,
основной отказ обеспечивает промпт) и трассировка редакций регламента (компаньоны в контексте).

### Режимы чанкера (env `CHUNKER`)

| Режим | recall@3 | Страницы в `sources[].page` | Когда использовать |
|---|---|---|---|
| `dense` (**по умолчанию**) | **92.6%** | страница начала чанка (≈) | максимальное качество поиска |
| `dense_pages` | 74.1% | точная у каждого фрагмента | нужна точная страница, качество вторично |
| `structured` | 66.7% | точная + секции | экспериментальный (деградирует на презентациях) |

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

См. `.env.example`: `LLM_API_URL` — адрес OpenAI-совместимого LLM (на платформе сабмита — DeepSeek V4.1 Flash через прокси организаторов); пусто → `llm: "stub"` в ответах.

## Документы

- Контракт API: [docs/API_CONTRACT.md](docs/API_CONTRACT.md) — менять только вместе с `service.py`, через PR.
- Гайд интеграции для бекенда: [docs/BACKEND_INTEGRATION.md](docs/BACKEND_INTEGRATION.md).

## Известные ограничения v0.1

- Генерация — заглушка (выжимка источников); настоящий LLM подключается через `LLM_API_URL` (платформа сабмита: DeepSeek V4.1 Flash).
- `/ingest` синхронный (большой PDF — десятки секунд); async — v0.2.
- Дедупликация по имени файла: заливка файла с тем же именем обновляет документ;
  один документ под разными именами = разные `doc_id` (по хэшу содержимого — v0.2).
- Индекс и uploads живут в volume; без volume рестарт контейнера = индекс с нуля.

## Порты и переменные окружения

| Переменная | По умолчанию | Смысл |
|---|---|---|
| `LLM_API_URL` | пусто | OpenAI-совместимый URL генерации; пусто → `llm: "stub"` в ответах |
| `DATA_DIR` | `ml/data/sample` | корпус для CLI-индексации (см. `config.py`) |
| `QDRANT_PATH` | `ml/.qdrant` | локальное хранилище индекса |

Порт: **8001** (Swagger `/docs`). Модель эмбеддингов: BAAI/bge-m3 (1024-dim, кэш HuggingFace).
Сабмит платформы: `submit/` — отдельная точка входа; env (`LLM_BASE_URL` и др.) подставляет платформа.
Для ИИ-агентов: сначала корневой `AGENTS.md`, затем `docs/API_CONTRACT.md` (машиночитаемая спецификация).
