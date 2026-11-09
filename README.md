# legal-assistant

ИИ-ассистент для юристов банка: юрист задаёт вопрос → система находит релевантные
фрагменты в документах → отвечает со ссылками на источники (RAG).
Кейс ПСБ × Changellenge, Hack&Change 2026.

## Команда и зоны

| Кто | Зона | Папка | Ветка |
|---|---|---|---|
| Svalbard1 | ML: поиск по документам + генерация | `ml/` | `ml/svalbard1` |
| Лиза, Валя | Backend: API, auth, БД, файлы | `backend/` | `be/liza`, `be/valya` |
| Гульсым | Frontend: чат, загрузка, источники | `frontend/` | `fe/gulsym` |

## Правила репозитория (коротко)

1. В `main` — только через Pull Request (1 approve). Каждое утро: `git pull origin main` в свою ветку.
2. Граница папок = граница ответственности: бекенд не коммитит в `ml/`, ML — в `backend/`, фронт — в `frontend/`.
3. Изменения контракта ML↔backend — только PR, меняющий `ml/docs/API_CONTRACT.md` и `ml/service.py` вместе; ревьюят ml + backend.
4. Секреты и большие файлы — никогда в git (`.env`, `venv/`, PDF/DOCX уже закрыты `.gitignore`).

## Архитектура

```
[Пользователь] → [Frontend React] → [Backend FastAPI: auth, сессии, PostgreSQL, MinIO]
                                          │ HTTP (контракт v0.1: ml/docs/API_CONTRACT.md)
                                          ▼
                        [ML FastAPI: /ingest, /ask, /health]  →  [Qdrant]
                                          └→ [vLLM Qwen2.5-32B — план]
```

## Быстрый старт (ML-сервис)

```bash
cd ml
pip install -r requirements.txt
uvicorn service:app --port 8001     # Swagger: http://localhost:8001/docs
```

Подробнее — [ml/README.md](ml/README.md).
Гайд для бекенда — [ml/docs/BACKEND_INTEGRATION.md](ml/docs/BACKEND_INTEGRATION.md).
Онбординги: [бекенд](ml/docs/ONBOARDING_BACKEND.md) · [фронтенд](ml/docs/ONBOARDING_FRONTEND.md).

## Статус (2026-11-09)

- ✅ Retrieval: bge-m3 (1024-dim) + Qdrant; HTTP API v0.1 (`/health`, `/ingest`, `/ask`); генерация — заглушка (`llm: "stub"`); тесты и чеклист приёмки — зелёные.
- 🔜 Реранкер bge-reranker-v2-m3, подключение vLLM, структурный чанкинг по пунктам договора, eval (RAGAS).
