# AGENTS.md — правила для ИИ-агентов (Cursor, Copilot, Claude и т.п.)

Первый файл для прочтения перед любыми изменениями в этом репозитории.
Проект: RAG-ассистент юристов банка (кейс ПСБ, Hack&Change 2026).

## Карта проекта

| Путь | Что там | Кто владеет |
|---|---|---|
| `ml/` | ML-сервис FastAPI (порт 8001): `/health`, `/ingest`, `/ask`; bge-m3 + Qdrant local | ML (Svalbard1) |
| `ml/submit/` | `solution.py` — сабмит на платформу автопроверки | ML |
| `ml/docs/` | Контракт API v0.1, гайды интеграции, онбординги | ML + backend (ревью) |
| `backend/` | Публичный API `/api/ask`, `/api/documents`; auth, PostgreSQL, MinIO | backend |
| `frontend/` | React-чат, загрузка документов, показ источников | frontend |

Порты: ML 8001 (Swagger `/docs`), backend 8000, frontend 5173.

## Жёсткие границы (нарушение = отклонение PR)

- **Агент бекенда**: не изменяй `ml/**`, `frontend/**`, корневые `docs/*.md`. Твоя зона — `backend/**`.
- **Агент фронта**: не изменяй `ml/**`, `backend/**`. Твоя зона — `frontend/**`.
- **Все агенты**: не коммить секреты, `ml/data/**` (база знаний, uploads), `ml/submission_*.zip`, виртуальные окружения.
- **Контракт ML↔backend**: `ml/docs/API_CONTRACT.md` и `ml/service.py` меняются только вместе, одним PR, с ревью Svalbard1. Если бекенду не хватает поля/эндпоинта — предложи правку контракта в PR-описании, а не ломай клиент.
- Материалы кейса (`ml/data/kb/`, PDF-ы) не публиковать: репозиторий публичный.

## Контракты (точные факты)

Полная спецификация: `ml/docs/API_CONTRACT.md`. Кратко — типы строгие, все поля присутствуют:

- `GET http://localhost:8001/health` → `{"status":"ok","chunks_indexed":int,"embed_model":str,"llm":"stub"|"vllm"}`
- `POST /ingest` (multipart/form-data, поле `file`; .pdf/.docx/.txt/.md; ≤25 МБ) →
  `200 {"doc_id":str(32 hex),"filename":str,"chunks":int,"status":"indexed"}`;
  ошибки `400` (формат/пустой текст), `413` (>25 МБ), `500` → `{"detail":str}`
- `POST /ask` (application/json `{"question":str 3..2000, "top_k":int 1..20, default 3}`) →
  `200 {"answer":str,"sources":[{"file":str,"text":str,"score":float}],"took_ms":int,"llm":str}`;
  ошибки `422` (валидация), `404` (ничего не найдено), `503` (индекс пуст)
- Идемпотентность: повторный `/ingest` того же файла обновляет документ (doc_id стабилен), дублей нет
- `llm:"stub"` → `answer` — детерминированная выжимка источников, НЕ сгенерированный текст
- Таймауты бекенда: `/health` 5 с, `/ingest` 180 с, `/ask` 90 с; ML недоступен → 502, таймаут → 504

## Как проверять изменения (обязательно перед PR)

```bash
cd ml
python3 -m pytest tests -q        # 18 тестов, ~10 с, модель не грузится
python3 -m ruff check .           # линтер, должен быть чистым
uvicorn service:app --port 8001   # ручная проверка: curl localhost:8001/health
```

Изменения, влияющие на поиск/чанкинг: `python3 eval.py` — baseline recall@3 = 92.6%,
MRR = 0.844. Ухудшение метрик = отклонение PR.

## Конвенции

- Python 3.11+ (совместимость с Docker `python:3.11-slim`), аннотации типов, docstrings по-русски.
- Коммит: `"<зона>: <что сделано>"` (примеры: `ml:`, `backend:`, `frontend:`, `docs:`).
- Ветки: `ml/svalbard1`, `be/*`, `fe/*`; фичи ветвятся от актуального `main`.
- ML-сервис запускается строго в один процесс (`uvicorn` без `--workers`) — локальный Qdrant держит lock.

## Известные ловушки

- Два процесса на одном `ml/.qdrant` = конфликт блокировки (409).
- Первый `/ask` после старта медленный (+5–20 с) — бекенд делает прогревочный запрос.
- `eval.py` требует актуальный индекс: сначала `python3 ingest.py`.
- Повторный `POST /ingest` файла с тем же именем обновляет документ — дублей не боимся.
- Материалы организаторов лежат в `ml/data/kb/` и в git не попадают (проверено .gitignore).
