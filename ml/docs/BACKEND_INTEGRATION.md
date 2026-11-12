# Гайд по интеграции: backend ↔ ML-сервис

**Кому:** бекенд — Лиза, Валя · **От:** ml (Svalbard1) · **Сопутствующий документ:** [API_CONTRACT.md](API_CONTRACT.md)

## 0. TL;DR — поднять ML-сервис у себя за 5 минут

```bash
cd ~/legal-assistant/ml
python3 -m venv venv && source venv/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cpu   # CPU-сборка, экономит ~2 ГБ
pip install -r requirements.txt          # fastapi + uvicorn уже внутри
uvicorn service:app --port 8001          # первый старт ~15–20 с (грузится модель), это нормально
```

Открыть http://localhost:8001/docs — живой Swagger по всем эндпоинтам.
Проверка: `curl http://localhost:8001/health` → `{"status": "ok", ...}`.

## 1. Что уже работает, а что заглушка

| Блок | Статус |
|---|---|
| Парсинг PDF/DOCX/TXT/MD → чанки | работает |
| Эмбеддинги bge-m3 + векторный поиск (Qdrant, локальный режим) | работает |
| HTTP API (`/health`, `/ingest`, `/ask`) | работает |
| Генерация ответа LLM | заглушка (`llm: "stub"`): возвращается выжимка источников. Когда подключим реальный LLM (OpenAI-совместимый; на платформе сабмита — DeepSeek V4.1 Flash через прокси организаторов), `answer` заполнится настоящим ответом — контракт не изменится |
| Аутентификация между бек и ML | нет (внутренний сервис); в контракте зарезервирован `X-API-Key` |

## 2. Структура папки ml/ (бекенд эту папку не меняет)

```
ml/
├── service.py               # FastAPI: /health, /ingest, /ask — точка стыковки
├── ingest.py                # парсинг + чанкинг + индексация (общий код CLI и сервиса)
├── retrieve.py              # CLI-поиск, удобно для отладки без HTTP
├── config.py                # пути, модель, размеры чанков
├── eval.py                  # golden-QA eval кейса: recall@k / MRR (27 вопросов)
├── eval_kb.py               # golden-QA на реальной базе организаторов
├── eval_hybrid.py           # эксперимент: гибрид dense+BM25 (RRF)
├── golden_qa.jsonl          # 27 эталонов кейса
├── golden_kb.jsonl          # 18 эталонов организаторов
├── requirements.txt         # + requirements-dev.txt (pytest, ruff — для тестов)
├── Dockerfile
├── .env.example             # LLM_API_URL
├── pyproject.toml           # политика ruff (исключения B008/BLE001/S110)
├── docs/                    # контракт и гайды (источник истины по стыку)
├── tests/                   # pytest: юнит + smoke API (быстрые, модель не грузится)
├── submit/                  # solution.py — сабмит на платформу (+ build_zip.py)
├── data/sample/             # тестовый пример.txt (коммитится), реальные PDF — нет
└── data/uploads/            # файлы, пришедшие через POST /ingest (в git не попадают)
```

## 3. Как дергать ML из бекенда

Готовый сниппет для FastAPI-бека (httpx):

```python
import httpx
from fastapi import HTTPException
from httpx import AsyncClient, Timeout

ml_client = AsyncClient(
    base_url="http://localhost:8001",      # в docker-compose: http://ml-service:8001
    timeout=Timeout(180.0, connect=5.0),   # общий запас: хватает и на /ingest, и на /ask
)

async def ml_ask(question: str, top_k: int = 3) -> dict:
    try:
        r = await ml_client.post("/ask", json={"question": question, "top_k": top_k})
        r.raise_for_status()
        return r.json()
    except httpx.TimeoutException:
        raise HTTPException(504, "ML-сервис не ответил вовремя")
    except httpx.HTTPStatusError as e:
        try:
            detail = e.response.json().get("detail", "ошибка ML-сервиса")
        except Exception:
            detail = "ошибка ML-сервиса"
        raise HTTPException(e.response.status_code, detail)
    except httpx.RequestError:
        raise HTTPException(502, "ML-сервис недоступен")
```

Правила:
- таймауты по каждому эндпоинту — таблица в контракте;
- `detail` из ответа ML можно писать в лог как есть — там человекочитаемое описание;
- после старта ml-сервиса сделать один прогревочный `/ask` (первый вызов грузит модель в память).

## 4. Переменные окружения

| Переменная | Сейчас | Зачем |
|---|---|---|
| `LLM_API_URL` | не задана (в `/health` будет `llm: "stub"`) | адрес OpenAI-совместимого прокси генерации; на платформе сабмита подставляется автоматически (DeepSeek V4.1 Flash), локально — любой такой LLM |
| `QDRANT_URL` | нет (Qdrant встроен, файл на диске) | появится в v0.2 при выносе Qdrant в отдельный контейнер |

Пути (индекс, папка данных) пока заданы в `ml/config.py`; внутри контейнера это `/app/.qdrant` и `/app/data/uploads`.

## 5. Docker

`ml/Dockerfile` уже в репо. Фрагмент docker-compose (бекенд — хозяин compose-файла):

```yaml
services:
  ml-service:
    build: ./ml
    ports: ["8001:8001"]
    environment:
      LLM_API_URL: ""                    # адрес OpenAI-совместимого прокси генерации (пусто → llm: "stub")
    volumes:
      - hf-cache:/root/.cache/huggingface   # иначе модель (~2 ГБ) качается заново при пересоздании
      - qdrant-data:/app/.qdrant            # иначе индекс теряется при рестарте
volumes:
  hf-cache:
  qdrant-data:
```

⚠️ Не добавляй `--workers` и `deploy.replicas`: ml-сервис работает в один процесс (см. «Ограничения v0.1» в контракте).

## 6. Чеклист приёмки стыковки

Прогоняется после первого соединения бек ↔ ml. Всё зелёное — стык считаем рабочим.

1. `GET /health` → 200, `chunks_indexed` ≥ 0
2. `POST /ingest` с файлом `ml/data/sample/пример.txt` → 200, `chunks` > 0
3. `POST /ask` «какая неустойка за просрочку поставки» → 200, `sources[0].file == "пример.txt"`, `score` > 0.5
4. `POST /ask` с `top_k: 0` → 422 с `detail`
5. `POST /ingest` файла 30 МБ → 413
6. `POST /ingest` файла `.exe` → 400
7. `POST /ask` до любого `/ingest` (пустой индекс) → 503
8. ml-контейнер остановлен → запрос бека возвращает 502/504 с понятным сообщением, а не голый 500
9. В ответе `/ask` поле `llm == "stub"` → фронт показывает «демо-режим»
10. http://localhost:8001/docs открывается, схемы совпадают с API_CONTRACT.md
11. Повторный `POST /ingest` того же файла → 200, тот же `doc_id`, `chunks_indexed` в `/health` не вырос (идемпотентность)

## 7. Кто чинит что (граница ответственности)

| Симптом | Чей баг |
|---|---|
| Источники нерелевантные, в чанках мусор | ml |
| `/ask` отвечает медленно (видно по `took_ms`) | ml |
| `answer` выглядит как выжимка, а не связный ответ | ml — но пока это ожидаемое поведение заглушки |
| 401/403 при логине, сессии, пользователи | backend |
| Аплоад > 25 МБ падает, не дойдя до ML | backend (собственный лимит должен быть не меньше ml-евского) |
| История диалогов, метаданные документов | backend |
| До `/ask` запрос идёт долго, но `took_ms` маленький | backend / сеть |

## 8. Процесс

- Изменения контракта: PR, меняющий `ml/docs/API_CONTRACT.md` и `ml/service.py` одновременно; ревьюят ml и backend.
- Бекенд не коммитит в `ml/`, ml не коммитит в `backend/` — граница папок = граница ответственности.
- Вопросы по API — в общий чат команды; спорные места фиксируем правкой контракта, а не устной договорённостью.

## Спецификация для ИИ-агента бекенда (точные правила интеграции)

- Клиент: `AsyncClient(base_url=ML_SERVICE_URL (env; default http://localhost:8001),
  timeout=Timeout(180.0, connect=5.0))`.
- `/ask`: проксировать JSON 1:1, не переименовывать поля; при ошибке ML возвращать клиенту
  ТОТ ЖЕ HTTP-код с `{"detail": ...}`; connection error → 502 «ML-сервис недоступен»,
  таймаут → 504 «ML не ответил вовремя».
- `/ingest`: проброс multipart (поле `file`); собственный лимит бекенда ≥ 25 МБ;
  повторная загрузка того же файла безопасна (ML идемпотентен) — ретраи разрешены.
- Прогрев: после старта бекенда один прогревочный `POST /ask` (модель ML грузится лениво 5–20 с).
- `/health` опрашивать каждые 10–30 с; `chunks_indexed` — метрика для статус-страницы.
- Запрещено: менять `ml/**`, хранить секреты в коде, дублировать логику поиска у себя,
  трогать `ml/submit/*` (зона ML-сабмита).
