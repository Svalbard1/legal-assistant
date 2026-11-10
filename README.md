# legal-assistant — ИИ-ассистент для юристов банка

Кейс ПСБ × Changellenge, Hack&Change 2026. RAG: юрист задаёт вопрос → система находит
релевантные фрагменты в базе знаний → отвечает со ссылками на положения документов и
уместно отказывается, если данных недостаточно.

> **ИИ-агентам (Cursor / Copilot / Claude и т.п.):** перед любыми изменениями прочти
> [AGENTS.md](AGENTS.md) — жёсткие границы зон, точные контракты и команды проверки.
> Полная спецификация API: [ml/docs/API_CONTRACT.md](ml/docs/API_CONTRACT.md).

## Состав системы и порты

| Компонент | Стек | Порт | Код | Статус |
|---|---|---|---|---|
| ML-сервис (RAG: поиск + генерация) | FastAPI, bge-m3, Qdrant (local) | **8001** | `ml/` | ✅ работает (v0.1) |
| Backend (auth, сессии, PostgreSQL, MinIO) | FastAPI | **8000** | `backend/` | 🚧 в разработке |
| Frontend (чат, загрузка файлов, источники) | React + Vite | **5173** | `frontend/` | 🚧 в разработке |
| Автосабмит платформы | Python stdlib | — | `ml/submit/solution.py` | ✅ валидирован |

Поток данных: пользователь → Frontend → Backend `POST /api/ask` → ML `POST /ask` (порт 8001)
→ Qdrant → ответ с `sources[]` → обратно по цепочке. Пользователь общается только с фронтом;
ML и Qdrant — внутренние сервисы, наружу не торчат.

## Команда и зоны

| Кто | Зона | Папка | Ветка |
|---|---|---|---|
| Svalbard1 | ML: поиск по документам + генерация | `ml/` | `ml/svalbard1` |
| Лиза, Валя | Backend: API, auth, БД, файлы | `backend/` | `be/liza`, `be/valya` |
| Гульсым | Frontend: чат, загрузка, источники | `frontend/` | `fe/gulsym` |

## Правила репозитория

1. `main` — только через Pull Request (защита ветки включена, 1 approve). Утром: `git pull origin main` в свою ветку.
2. Граница папок = граница ответственности: бекенд не коммитит в `ml/`, ML — в `backend/`, фронт — в `frontend/` и `docs/`.
3. Контракт ML↔backend (`ml/docs/API_CONTRACT.md` + `ml/service.py`) меняется только одним PR с ревью ml + backend.
4. Секреты — только в `.env` (в git не попадают); материалы базы знаний и PDF кейса в git не публикуются.

## Быстрый старт (ML-сервис)

```bash
cd ml
pip install -r requirements.txt
uvicorn service:app --port 8001     # Swagger: http://localhost:8001/docs
```

⚠️ Ровно один процесс (`uvicorn` без `--workers`): локальный Qdrant держит файл блокировкой.
Первый `/ask` медленный (~20 с, ленивая загрузка модели) — сделайте прогревочный запрос.

## Переменные окружения ML

| Переменная | По умолчанию | Эффект |
|---|---|---|
| `LLM_API_URL` | пусто | Пусто → `llm: "stub"` (answer = выжимка источников). OpenAI-совместимый URL → `llm: "vllm"` (настоящая генерация) |
| `DATA_DIR`, `QDRANT_PATH` | `ml/data/sample`, `ml/.qdrant` | Пути заданы в `ml/config.py` (env-вынос — v0.2) |
| `CHUNKER` | `dense` | Режим чанкера: `dense` / `dense_pages` (точные страницы, −18 п.п. recall@3) / `structured` (эксперим.) |

Сабмит платформы получает свои `LLM_BASE_URL`/`LLM_API_KEY`/`LLM_MODEL` автоматически — см. [ml/submit/README.md](ml/submit/README.md).

## Качество поиска (eval)

`python eval.py` — recall@k, MRR на 27 golden-вопросах. Baseline (2026-11-09):
recall@3 = **92.6%**, recall@10 = **100%**, MRR = **0.844**. Любое изменение пайплайна
сверяется цифрами «до/после» — ухудшение = отклонение PR.

## Документы (полный указатель)

| Документ | Для кого | Что внутри |
|---|---|---|
| [AGENTS.md](AGENTS.md) | ИИ-агенты | границы, контракты кратко, команды проверки |
| [ml/docs/API_CONTRACT.md](ml/docs/API_CONTRACT.md) | бекенд + агенты | полная спецификация API v0.1: типы, ошибки, таймауты, лимиты |
| [ml/docs/BACKEND_INTEGRATION.md](ml/docs/BACKEND_INTEGRATION.md) | бекенд | подъём за 5 мин, httpx-сниппет, чеклист 11 пунктов, «чей баг» |
| [ml/docs/ONBOARDING_BACKEND.md](ml/docs/ONBOARDING_BACKEND.md) | бекенд | git-онбординг + план работ по фазам |
| [ml/docs/ONBOARDING_FRONTEND.md](ml/docs/ONBOARDING_FRONTEND.md) | фронт | онбординг + формат данных + состояния UI |
| [ml/README.md](ml/README.md) | ML + все | запуск, тесты, eval, структура ml/ |
| [ml/submit/README.md](ml/submit/README.md) | ML | сабмит платформы: регламент, лимиты, логика |
| [frontend/TASKS.md](frontend/TASKS.md) | фронт (Гульсым) | задачи с критериями приёмки + демо-скрипт 90 сек для жюри |

## Статус (2026-11-10)

- ✅ Retrieval bge-m3 + Qdrant; HTTP API v0.1 (`/health`, `/ingest`, `/ask`) — тесты 18/18, чеклист приёмки 11/11
- ✅ Eval-харнесс (recall@k/MRR); `solution.py` для платформы — валидирован на реальной базе организаторов (203.8 с, 18/18 ответов)
- ✅ Генерация — заглушка (`llm: "stub"`); материалы организаторов разобраны (база 21 документ, форматы вопросов/ответов)
- 🔜 Структурный чанкинг по пунктам + номера страниц; отказ-логика по 5 сценариям кейса; реранкер Qwen3 Reranker 8B (опционально); async ingest, фильтр `doc_ids`, `X-API-Key`, история диалога (v0.2)
