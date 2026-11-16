# Legal Assistant — RAG-ассистент для работы с документами

Проект Hack&Change 2026: система ищет по загруженным юридическим документам и отвечает с цитатами из найденных фрагментов. Поиск выполняется локально через эмбеддинги `BAAI/bge-m3` и Qdrant embedded. По умолчанию генерация выключена: сервис возвращает детерминированную выжимку источников (`llm: "stub"`). При необходимости можно подключить внешний OpenAI-совместимый LLM API.

## Состав и готовность

| Компонент | Реализация | Порт | Состояние |
|---|---|---:|---|
| ML/RAG API | FastAPI, bge-m3, Qdrant embedded, BM25 + dense retrieval | 8001 | Реализован: `/health`, `/ingest`, `/ask` |
| Backend API | FastAPI, PostgreSQL, история диалогов | 8000 | Реализованы health, ask и API истории; загрузка документа через backend пока не реализована |
| Web UI | React + Vite | 5173 | Клиент чата; отдельный dev-сервер, в Docker Compose не включён |
| Автосабмит | `ml/submit/solution.py` | — | Отдельное решение для платформы, не является способом запуска локального веб-приложения |

Поток запроса: браузер → Backend `/api/ask` → ML `/ask` → поиск по Qdrant → ответ и источники. Загрузка документов в текущей сборке выполняется напрямую в ML API через `POST /ingest`.

## Требования

- Docker Engine с Compose v2 (`docker compose`)
- Для локального запуска без Docker: Python 3.11+ для ML, Python 3.12+ для Backend, Node.js/npm для UI
- Доступ в интернет при первом запуске ML: скачиваются Docker-образы и модель `BAAI/bge-m3` (кэшируется в Docker volume)
- Для создания ZIP-сабмита см. [`ml/submit/README.md`](ml/submit/README.md)

## Запуск сервисов через Docker Compose

Из корня репозитория:

```bash
cp .env.example .env
docker compose up -d --build --wait postgres ml-service
docker compose run --rm --no-deps \
  -e ALEMBIC_DB_HOST=postgres \
  -e ALEMBIC_DB_PORT=5432 \
  backend alembic -c /app/alembic.ini upgrade head
docker compose up -d backend
```

Это поднимает PostgreSQL, ML API и Backend. Первый старт ML может занять время на скачивание модели. Миграции PostgreSQL обязательны перед первым запуском Backend и после обновлений схемы.

Проверка:

```bash
curl http://localhost:8001/health
curl http://localhost:8000/health
```

- ML Swagger: <http://localhost:8001/docs>
- Backend OpenAPI: <http://localhost:8000/docs>
- PostgreSQL с хоста доступен на `localhost:5433`; внутри Compose Backend подключается к `postgres:5432`.

Остановить сервисы, сохранив данные в volumes:

```bash
docker compose down
```

Удалить также данные БД, индекс и кэш модели:

```bash
docker compose down -v
```

### Запуск Web UI

Frontend не входит в Compose — запустите его отдельным процессом. Пока Compose-сервисы работают:

```bash
cd frontend
npm ci
npm run dev -- --host 0.0.0.0
```

Откройте адрес Vite, обычно <http://localhost:5173>. Для смены URL Backend задайте `VITE_API_BASE_URL` (см. [`frontend/.env.example`](frontend/.env.example)); переменные `VITE_*` встраиваются в клиентский код и не должны содержать секретов.

> Итого, сейчас нет единственной команды, которая поднимает все компоненты приложения: Compose запускает Backend, ML и PostgreSQL, миграция выполняется отдельной командой, а UI запускается через npm отдельно.

## Первый запрос и загрузка документа

ML API принимает `.pdf`, `.docx`, `.txt` и `.md` размером до 25 МБ. Пример с тестовым текстом из репозитория:

```bash
curl -F "file=@ml/data/sample/пример.txt" http://localhost:8001/ingest
curl -X POST http://localhost:8001/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"Какие условия указаны в документе?","top_k":3}'
```

В ответе `/ask` находятся `answer`, `sources`, `took_ms` и `llm`; подробности и ограничения — в [контракте ML API](docs/API_CONTRACT.md). Backend API включает `/api/ask`, `/api/sessions` и `/api/sessions/{session_id}/messages`; описание схем смотрите в `/docs` запущенного Backend.

## Конфигурация и секреты

Шаблон корневого окружения: [`.env.example`](.env.example). Перед запуском скопируйте его в `.env`; пример содержит только локальные значения/пустые настройки, замените `POSTGRES_PASSWORD` на собственный пароль. Не помещайте рабочие ключи или пароли в Git, Docker-образы, публичный README либо ZIP.

| Переменная | Используется | Назначение |
|---|---|---|
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Compose, Backend, Alembic | Настройки PostgreSQL. Для локального примера поменяйте пароль перед использованием вне изолированной разработки. |
| `POSTGRES_HOST`, `POSTGRES_PORT` | Backend при запуске вне Compose | Адрес БД; в Compose Backend получает внутренние `postgres:5432`. |
| `DATABASE_URL` | Backend (необязательно) | Полный DSN, если нужно переопределить автоматически собранное соединение. |
| `ML_SERVICE_URL` | Backend | URL ML API; в Compose задаётся как `http://ml-service:8001`. |
| `LLM_API_URL` | ML (необязательно) | Base URL OpenAI-совместимого API; пустое значение оставляет stub-режим. |
| `LLM_API_KEY`, `LLM_MODEL` | ML (необязательно) | Ключ и имя модели выбранного провайдера; ключ передаётся как Bearer-токен. Храните его только в локальном `.env`/секрет-хранилище. |
| `TEMPERATURE`, `MAX_TOKENS` | ML (необязательно) | Параметры генерации; по умолчанию `0.0` и `1024`. |
| `VITE_API_BASE_URL` | Frontend | URL Backend для браузерного клиента; шаблон — `frontend/.env.example`. |

Пути индекса и загрузок ML сейчас заданы в `ml/config.py`: `ml/.qdrant` и `ml/data/uploads`. В Compose Qdrant хранится в volume `qdrant-data`, кэш Hugging Face — в `hf-cache`. Для тестового/демо-запуска API `/ingest` загрузите документ после старта: индекс формируется по загруженным файлам, не по содержимому Docker-образа.

## Подключение внешнего LLM API (необязательно)

Локальная система не требует внешнего API для поиска и запуска. Без `LLM_API_URL` поле `llm` имеет значение `stub`, а ответ — выжимка найденных источников, не генерация моделью.

Чтобы включить генерацию, используйте провайдера с OpenAI-совместимым endpoint `POST {LLM_API_URL}/chat/completions`:

1. Получите у выбранного провайдера base URL, API key и идентификатор доступной модели.
2. Запишите их в локальный `.env` (не в Git):

   ```dotenv
   LLM_API_URL=https://provider.example/v1
   LLM_API_KEY=replace-with-your-local-secret
   LLM_MODEL=provider-model-id
   ```

3. Передайте эти переменные ML-контейнеру. Сейчас корневой `docker-compose.yml` явно задаёт `LLM_API_URL` пустым и не прокидывает ключ/модель. Поэтому для Compose нужно добавить в секцию `ml-service.environment` значения из окружения, например `LLM_API_URL: ${LLM_API_URL:-}`, `LLM_API_KEY: ${LLM_API_KEY:-}` и `LLM_MODEL: ${LLM_MODEL:-}`, затем пересоздать сервис командой `docker compose up -d --build ml-service`.
4. Проверьте `GET http://localhost:8001/health`: при настроенном URL API поле `llm` указывает `vllm`. Вызов API тарифицируется и обрабатывается по условиям выбранного провайдера; не отправляйте туда конфиденциальные документы без разрешения и соответствующей настройки обработки данных.

`LLM_API_URL`, `LLM_API_KEY`, `LLM_MODEL` — имена переменных ML-сервиса; также распознаются совместимые алиасы `LLM_BASE_URL`/`OPENAI_BASE_URL`, `OPENAI_API_KEY` и `GEN_MODEL`/`OPENAI_MODEL`. Реализация вызывает chat completions, а не использует внешний API для эмбеддингов: эмбеддинги строятся локально через `BAAI/bge-m3`.

## Сборка и зависимости

- ML: `ml/Dockerfile`, версии Python-зависимостей закреплены в [`ml/requirements.txt`](ml/requirements.txt); CPU-сборка PyTorch задаётся в Dockerfile.
- Backend: `backend/Dockerfile`, версии закреплены в [`backend/requirements.txt`](backend/requirements.txt).
- Frontend: [`frontend/package-lock.json`](frontend/package-lock.json) фиксирует npm-дерево; используйте `npm ci`.
- Корневой [`docker-compose.yml`](docker-compose.yml) описывает PostgreSQL, ML и Backend. [`.dockerignore`](.dockerignore) исключает Git, виртуальные окружения и `.env` из Docker build context.

Для публикации проекта архивируйте исходники и конфигурацию, необходимые для сборки; не добавляйте `.env`, кэши, виртуальные окружения, `.qdrant`, пользовательские загрузки, секреты и закрытые материалы кейса. Учтите: реальная база знаний из `ml/data/kb/` не распространяется; для демонстрации загрузите разрешённые документы самостоятельно. Для требуемого финальной проверкой Docker-запуска «всё одной командой» необходимо дополнительно контейнеризовать frontend и автоматизировать применение миграций — в текущем репозитории этого нет.

## Проверка

ML (команды выполняются из `ml/`):

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m pytest tests -q
python3 -m ruff check .
```

Backend (из корня; PostgreSQL должен быть доступен, тестовая БД — настроена):

```bash
python3 -m pip install -r backend/requirements.txt
python3 -m pip install pytest pytest-asyncio
pytest backend/tests -q
```

Тесты Backend требуют отдельную БД `legal_assistant_test` на `localhost:5433` с таблицами, созданными миграциями. Текущая Compose-конфигурация автоматически создаёт только основную БД `legal_assistant`; одной команды `pytest` без предварительной настройки тестовой БД недостаточно.

Frontend:

```bash
cd frontend
npm ci
npm run lint
npm run build
```

Retrieval-eval зависит от доступного корпуса и индекса; порядок запуска и метрики описаны в [`ml/README.md`](ml/README.md). Не запускайте eval на закрытых материалах в публичной CI-среде.

## Структура и дополнительные инструкции

```text
backend/             Backend API, миграции и тесты
frontend/            React/Vite UI и package-lock.json
ml/                  RAG API, индексация, retrieval, тесты
ml/submit/           Автономное решение для платформенного ZIP-сабмита
docs/                API-контракт и интеграционные документы
docker-compose.yml   Локальная инфраструктура (PostgreSQL, ML, Backend)
```

- [ML: запуск, тесты и eval](ml/README.md)
- [API-контракт ML](docs/API_CONTRACT.md)
- [Инструкция платформенного сабмита и ZIP](ml/submit/README.md)
- [Правила работы с репозиторием](AGENTS.md)