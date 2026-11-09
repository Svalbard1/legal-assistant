# Техническое резюме диалога: проект legal-assistant

> ⚠️ **Исторический снимок от 2026-11-09.** Разделы про vLLM / Qwen2.5-32B-Instruct-AWQ и реранкер bge-reranker-v2-m3 устарели: по Техническому регламенту платформа сабмита предоставляет DeepSeek V4.1 Flash, BAAI/bge-m3 и Qwen3 Reranker 8B через OpenAI-совместимый прокси (env: LLM_BASE_URL / LLM_API_KEY / LLM_MODEL). Актуально: ml/submit/README.md и ml/docs/API_CONTRACT.md.

**Назначение:** перенос контекста в другой AI-инструмент. Составлено 2026-11-09 по итогам одной рабочей сессии.
**Принцип:** ничего не выдумано; всё перечисленное либо сделано и проверено, либо явно помечено как план / не подтверждено.
**Пользователь:** Svalbard1 — ML-разработчик в команде из 4 человек, новичок в Git (значительная часть диалога — обучающая). ОС Linux, bash, VS Code, есть conda (base), рабочий venv в `ml/venv` (имя без точки).

---

## 1. Цель проекта

Кейс **«ИИ-ассистент для юристов банка»** (ПСБ × Changellenge, Hack&Change 2026). Строится RAG-система: юрист задаёт вопрос → поиск релевантных фрагментов по базе документов → ответ со ссылками на источники.

- Репозиторий: `https://github.com/Svalbard1/legal-assistant.git` — **публичный** (решение пользователя, отсюда упрощённый git-процесс и жёсткий запрет секретов в коде).
- Команда и личные ветки (длинные, на весь проект): `ml/svalbard1` (пользователь), `be/petr`, `be/second` (бекенд), `fe/anna` (фронт). Конкретные имена веток — договорённость внутри команды.
- Подцель диалога: онбординг новичка в Git — в начале сессии создана шпаргалка `download/Git_GitHub_для_новичка_шпаргалка.docx` (+ PDF, 9 страниц).

## 2. Техническая архитектура

Целевая схема (согласована в диалоге):

```
[Пользователь]
   │ HTTPS
[Frontend React — fe/anna]                чат, загрузка файлов, показ источников
   │ /api/ask, /api/documents
[Backend FastAPI — be/petr, be/second]    auth, сессии, PostgreSQL, история, MinIO
   │ /ask, /ingest   ← ГРАНИЦА ОТВЕТСТВЕННОСТИ (HTTP-контракт v0.1)
[ML-сервис FastAPI — ml/svalbard1]        retrieval + генерация
   │
[Qdrant]   [vLLM на GPU-сервере]          (vLLM — план; пока заглушка llm_stub)
```

**Правила границы** (зафиксированы): бекенд не коммитит в `ml/`, ML не коммитит в `backend/`; изменения контракта — только PR, ревьюят ml+backend; спорные баги маршрутизируются по правилу «нерелевантные источники / мусор в чанках / выдумки → ml; 401 / большие файлы / история → бекенд; медленно в `/ask` (по `took_ms`) → ml, медленно до `/ask` → бекенд/сеть».

**Фактическое состояние на конец сессии:** работает автономный ML-скелет без HTTP (CLI `ingest.py` / `retrieve.py`, локальный Qdrant, 55 чанков в коллекции `legal_docs`). FastAPI-обёртка (`service.py`) написана и проверена синтаксически, но пользователем не запускалась и в репо не закоммичена (подтверждения нет).

## 3. Используемые технологии

- Python 3.11 (в Docker — `python:3.11-slim`).
- Эмбеддинги: `sentence-transformers>=3.0,<4`, модель **BAAI/bge-m3** (1024-мерные векторы, многоязычная). Кэш модели — `~/.cache/huggingface` (~2.3 ГБ скачаны один раз, в репо не хранится).
- Векторное хранилище: `qdrant-client>=1.10,<2` в **локальном режиме** (`QdrantClient(path=...)`, файл `ml/.qdrant`, без сервера).
- Парсинг документов: `pypdf>=4.0` (PDF), `python-docx>=1.1` (DOCX), txt/md напрямую.
- HTTP-слой ML: `fastapi>=0.115`, `uvicorn[standard]>=0.30`, `python-multipart>=0.0.9`, pydantic-схемы.
- LLM (план): Qwen2.5-32B-Instruct-AWQ через vLLM на отдельном GPU-сервере (~20+ ГБ VRAM, RTX 3090/4090). Разработка у всех на CPU.
- Реранкер (план): `bge-reranker-v2-m3` поверх топ-10.
- Бекенд (план): FastAPI, httpx (AsyncClient), PostgreSQL, MinIO, docker-compose. Фронт (план): React.
- Git: HTTPS + PAT (Personal Access Token), `credential.helper store`.

## 4. Принятые архитектурные решения

1. Публичный репозиторий → git-аутентификация по **PAT**, не по паролю; все секреты — только в `.env` (в `.gitignore`).
2. Git-процесс: **main только через PR**; утром каждому — `git pull origin main` в свою ветку (главное анти-конфликтное правило); PR небольшие (1–2 дня работы), 1 approve, мержит автор, личные ветки не удаляются; force-push запрещён.
3. **Contract-first**: HTTP-контракт бекенд↔ML зафиксирован документом ДО реализации стыковки; Swagger на `/docs` генерируется из кода и считается живой документацией.
4. ML — отдельный FastAPI-сервис с эндпоинтами `POST /ingest`, `POST /ask`, `GET /health`.
5. Для разработки Qdrant во **встроенном (local) режиме**; вынос в отдельный контейнер зарезервирован под v0.2 (`QDRANT_URL`).
6. Параметры retrieval: `CHUNK_SIZE=500` символов, `CHUNK_OVERLAP=50`, `TOP_K=3`, косинусная метрика, коллекция `legal_docs`.
7. **Заглушка LLM**: поле `answer` уже в контракте с финальным форматом; содержимое пока — выжимка источников; флаг `llm: "stub"|"vllm"` в ответах (фронт по нему показывает «демо-режим»). Подключение vLLM не меняет контракт.
8. Тяжёлые объекты (модель эмбеддингов, Qdrant-клиент) инициализируются **лениво**, при первом запросе.
9. v0.1 — синхронные эндпоинты; ограничения честно задокументированы в контракте (§5), асинхронность — v0.2.
10. Сервис строго **однопроцессный** (запрет `--workers`/`replicas`): локальный Qdrant не рассчитан на несколько процессов над одним путём.
11. Реальные документы (PDF/DOCX) в git не попадают (`ml/data/**/*.pdf`, `ml/data/**/*.docx` в `.gitignore`); в репо лежит синтетический тестовый `пример.txt`.
12. Разработка на CPU у каждого; GPU нужен только под LLM на общем сервере, все обращаются по API.
13. CORS `*` — только dev; сервис внутренний; `X-API-Key` зарезервирован на v0.2.
14. Загруженные через API файлы сохраняются в `DATA_DIR` (`ml/data/sample`), `doc_id` генерируется как `uuid4().hex`.

## 5. Реализованные компоненты

**В репо (ветка ml/svalbard1) — написано и проверено:**
- `ml/config.py` (10 строк), `ml/ingest.py` (72), `ml/retrieve.py` (31), `ml/requirements.txt`, `ml/README.md`
- `ml/data/sample/пример.txt` — синтетический договор поставки № 47-2025/ТП (ООО «Ромашка» / ООО «Василёк», мебель, 1 200 000 руб., неустойка 0,1%/день, Арбитражный суд Москвы) — 6 чанков
- `.gitignore` в корне (полный текст в §6)
- Проверка пайплайна: `ingest.py` проиндексировал `ПСБ_кейс.pdf` → **49 чанков**, `пример.txt` → **6** (итого 55); `retrieve.py` на трёх контрольных запросах вернул правильный фрагмент топ-1: «какая неустойка за просрочку поставки» → п. 4.1 (score 0.692), «размер предоплаты по договору» → п. 2.2 (0.600), «какой суд рассматривает споры» → п. 5.2 (0.498 — семантическое совпадение без общих слов)
- `git add --dry-run` чистый (7 файлов); коммит упёрся в отсутствие git identity — решение дано (§7), статус коммита/PR **не подтверждён**

**Пакет передачи бекенду — создан, лежит в `download/backend_handoff/` (файлы py_compile-проверены; в репо предполагается: docs → `ml/docs/`, `service.py` и `Dockerfile` → `ml/`; закоммичены ли — не подтверждено):**
- `API_CONTRACT.md` — контракт v0.1 (см. ниже)
- `BACKEND_INTEGRATION.md` — гайд: подъём за 5 минут, httpx-сниппет, env, docker-compose, чеклист приёмки (10 пунктов), таблица «чей баг», процесс
- `service.py` (161 строка) — FastAPI-сервис v0.1.0
- `Dockerfile` (9 строк)

**Контракт v0.1 (ключевые положения):**
- `GET /health` → `{status:"ok", chunks_indexed:int, embed_model:str, llm:"stub"|"vllm"}`; таймаут бекенда 5 с
- `POST /ingest`: multipart, поле `file`; форматы `.pdf/.docx/.txt/.md`; лимит **25 МБ**; синхронный; → 200 `{doc_id, filename, chunks, status:"indexed"}`; ошибки: 400 (формат / в файле нет текста), 413 (>25 МБ), 500
- `POST /ask`: `{question: 3–2000 символов, top_k: 1–20, default 3}` → 200 `{answer, sources:[{file, text, score}], took_ms, llm}`; ошибки: 422 (валидация), 404 (ничего не найдено), 503 (индекс пуст); таймаут бекенда 90 с; ingest — 180 с
- Ограничения v0.1: `llm=stub`; ingest синхронный и **без дедупликации** (повтор = дубликаты чанков); один процесс; индекс/файлы в volume (без volume рестарт = индекс с нуля); CORS `*`
- Зарезервировано под v0.2: async ingest (`202 {task_id}` + `GET /ingest/{doc_id}/status`), `sources[].doc_id` и `page`, фильтр `{"doc_ids":[...]}`, дедупликация по хэшу файла, `X-API-Key`, `QDRANT_URL`

## 6. Фрагменты кода, которые важно сохранить

**`ml/config.py` (полностью):**
```python
from pathlib import Path

ML_DIR = Path(__file__).resolve().parent
DATA_DIR = ML_DIR / "data" / "sample"
QDRANT_PATH = ML_DIR / ".qdrant"      # локальное хранилище, в git не попадёт

EMBED_MODEL = "BAAI/bge-m3"           # 1024-мерные эмбеддинги
COLLECTION = "legal_docs"
CHUNK_SIZE = 500                      # символов на чанк
CHUNK_OVERLAP = 50
TOP_K = 3
```

**`ml/ingest.py` — ключевые функции (файл 72 строки, проверен запуском):**
```python
def read_text(path: Path) -> str:
    """Текст из pdf / docx / txt / md."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        from pypdf import PdfReader
        return "\n".join(p.extract_text() or "" for p in PdfReader(str(path)).pages)
    if suffix == ".docx":
        import docx
        return "\n".join(p.text for p in docx.Document(str(path)).paragraphs)
    return path.read_text(encoding="utf-8")


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Режем на перекрывающиеся куски, стараясь не рвать предложения."""
    chunks, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            for sep in ("\n", ". ", " "):
                cut = text.rfind(sep, start, end)
                if cut > start + size // 2:
                    end = cut + len(sep)
                    break
        chunks.append(text[start:end].strip())
        start = end - overlap if end < len(text) else end
    return [c for c in chunks if c]
```
Логика индексации (и в CLI, и в `/ingest`): если коллекции нет — `create_collection(COLLECTION, vectors_config=VectorParams(size=1024, distance=Distance.COSINE))`; `start_id = client.count(COLLECTION).count`; `vectors = model.encode(chunks)`; `client.upsert(...)` с `PointStruct(id=start_id+i, vector=v.tolist(), payload={...})`.

**`ml/service.py` — модели контракта, env и заглушка LLM (полный файл в `download/backend_handoff/service.py`):**
```python
MAX_UPLOAD_MB = 25
ALLOWED_SUFFIXES = {".pdf", ".docx", ".txt", ".md"}
VECTOR_SIZE = 1024
LLM_API_URL = os.environ.get("LLM_API_URL", "")   # "vllm" если задана, иначе "stub"

class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    top_k: int = Field(default=TOP_K, ge=1, le=20)

class Source(BaseModel):
    file: str
    text: str
    score: float

class AskResponse(BaseModel):
    answer: str
    sources: list[Source]
    took_ms: int
    llm: str
# IngestResponse(doc_id, filename, chunks, status); HealthResponse(status, chunks_indexed, embed_model, llm)

def llm_stub(question: str, sources: list[Source]) -> str:
    """Заглушка генерации до подключения vLLM: выжимка найденных фрагментов."""
    lines = [f"Вопрос: {question}", "",
             f"Найдено {len(sources)} фрагментов. Генерация LLM ещё не подключена (llm=stub), "
             "ниже — выдержки из источников:"]
    for i, s in enumerate(sources, 1):
        lines.append(f"{i}. [{s.file}, score={s.score}] {s.text[:200].strip()}...")
    return "\n".join(lines)
```
Поведение эндпоинтов: ленивые `get_model()` / `get_client()`; `/ingest` — синхронный `def` (threadpool), сохраняет файл в `DATA_DIR`, пустой текст → `HTTPException(400)`, payload точки — `{"doc_id", "file", "text"}`; `/ask` — 503 если коллекции нет, 404 если нет хитов, score округляется до 4 знаков, `took_ms` через `time.monotonic()`; CORS `*` (dev).

**Сниппет для бекенда (из BACKEND_INTEGRATION.md):**
```python
ml_client = AsyncClient(base_url="http://localhost:8001",   # в compose: http://ml-service:8001
                        timeout=Timeout(180.0, connect=5.0))

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

**`ml/Dockerfile` (полностью) и фрагмент docker-compose бекенда:**
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# CPU-сборка torch в 4 раза меньше образа; раскомментируй, если контейнер точно без GPU:
# RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
COPY . .
EXPOSE 8001
CMD ["uvicorn", "service:app", "--host", "0.0.0.0", "--port", "8001"]
```
```yaml
services:
  ml-service:
    build: ./ml
    ports: ["8001:8001"]
    environment:
      LLM_API_URL: ""                    # заполнить при подключении vLLM
    volumes:
      - hf-cache:/root/.cache/huggingface   # иначе модель (~2 ГБ) качается заново
      - qdrant-data:/app/.qdrant            # иначе индекс теряется при рестарте
volumes:
  hf-cache:
  qdrant-data:
```
(⚠️ без `--workers` и `deploy.replicas` — см. решение 10.)

**`.gitignore` (корень репо, полный):**
```gitignore
.env
.env.*
!.env.example
__pycache__/
*.py[cod]
.venv/
venv/
.pytest_cache/
.ruff_cache/
.mypy_cache/
.coverage
htmlcov/
ml/.qdrant/
ml/data/**/*.pdf
ml/data/**/*.docx
ml/models/
node_modules/
dist/
build/
.idea/
.vscode/
.DS_Store
Thumbs.db
```

**`ml/requirements.txt` (итоговый состав):**
```
sentence-transformers>=3.0,<4
qdrant-client>=1.10,<2
pypdf>=4.0
python-docx>=1.1
fastapi>=0.115
uvicorn[standard]>=0.30
python-multipart>=0.0.9
```

## 7. Найденные проблемы и их решения

1. **`retrieve.py` молча ничего не выводил** → файл был пуст на диске (0 строк): код вставлялся в VS Code, но не сохранялся (точка ● на табе). Решение: Ctrl+S; контроль `wc -l` (итог: config.py — 10, ingest.py — 72, retrieve.py — 31 строк). Общий урок: «молчаливый мгновенный выход» → сначала `wc -l файл`.
2. **`venv/bin/activate: Отказано в доступе`** (+ безуспешный `sudo`) → activate — скрипт для source, не исполняемый файл: `source venv/bin/activate`. Sudo не нужен.
3. **Опечатка `requirement.txt`** → переименовано в `requirements.txt` (pip по-другому не найдёт).
4. **.gitignore закрывал `ml/.venv/`, а папка называется `venv`** → правило заменено на `venv/` (иначе git попытался бы закоммитить гигабайты). Если уже в индексе: `git rm -r --cached ml/venv`.
5. **GitHub отклонил пароль аккаунта** (`Password authentication is not supported for Git operations`) → нужен PAT: `https://github.com/settings/tokens/new?scopes=repo&description=legal-assistant`, затем `git config --global credential.helper store`; при пуше Username `Svalbard1`, Password = токен (вставлять Ctrl+Shift+V, символы не отображаются).
6. **Ошибка `askpass.sh`** (путь `/snap/code/255/...`) → устаревший путь snap после обновления VS Code; `unset GIT_ASKPASS` или полный перезапуск VS Code.
7. **`git commit`: «Author identity unknown»** → `git config --global user.name "Svalbard1"` + `user.email` = почта GitHub; для публичного репо рекомендован noreply-адрес вида `12345678+Svalbard1@users.noreply.github.com` (Settings → Emails → «Keep my email addresses private»).
8. **«a branch named 'ml/svalbard1' already exists»** → не ошибка: ветка уже создана, просто `git switch ml/svalbard1`.
9. **ingest и retrieve запущены одной строкой** → retrieve отработал до завершения индексации; команды запускать раздельно.
10. **Артефакты `\n` в тексте из PDF** (pypdf) → не-блокер; запланирована очистка текста перед чанкингом.
11. **Score ~0.49 на абстрактных запросах** против 0.60–0.69 на конкретных → норма для bge-m3; ожидаемое улучшение — реранкер.
12. **Нюанс (не баг):** CLI `ingest.py` пишет payload `{"file", "text"}` без `doc_id`; `service.py` добавляет `"doc_id"`. Поиск читает только `file`/`text`, поэтому не ломается; унифицировать в v0.2.

## 8. Нереализованные задачи

Ближайшие (порядок назывался в диалоге; оба — «следующий шаг после merge»):
1. Закоммитить/смержить ML-скелет (identity исправлена, результат не подтверждён) и пакет передачи бекенда; добавить в `ml/requirements.txt` три зависимости из §6.
2. Протестировать `service.py` локально: `uvicorn service:app --port 8001` (первый старт ~15–20 с), `/docs`, curl-тройка health/ingest/ask.
3. Реранкер `bge-reranker-v2-m3` поверх топ-10 (назван следующим шагом после merge первого PR).
4. Подключить vLLM (Qwen2.5-32B-Instruct-AWQ) на GPU-сервере, заменить `llm_stub` на реальную генерацию, задать `LLM_API_URL` (назван следующим шагом после merge пакета передачи).
5. Очистка текста PDF перед чанкингом (артефакты `\n`).

Бекенд (be/petr, be/second) — по гайду:
6. Скелет `backend/`: публичный API `/api/ask`, `/api/documents` (auth, rate-limit), httpx-клиент к ML (сниппет готов), PostgreSQL (диалоги, метаданные), MinIO (файлы), docker-compose (фрагмент готов), прогон чеклиста приёмки из 10 пунктов (включая проверку 502/504 при остановленном ML и плашку «демо-режим» по `llm=="stub"`).

Фронт (fe/anna):
7. Чат, загрузка файлов, показ `sources`, плашка «демо-режим» по полю `llm`.

Контракт v0.2:
8. Async ingest + статусы, дедупликация по хэшу, `sources[].doc_id`/`page`, фильтр `doc_ids`, `X-API-Key`, вынос Qdrant в контейнер (`QDRANT_URL`), вынос путей в env.

Прочее:
9. Branch protection на main (Settings → Branches → Add branch rule → Require a pull request before merging + Require approvals 1; для публичных репо бесплатно) — предложено, включение не подтверждено.
10. RAGAS-оценка качества retrieval+генерации (упоминалась как часть зоны ML).
11. В репо нужен владелец docker-compose — бекенд; CI-файл (ruff+pytest) был в первой шпаргалке, в репо не создавался.

## 9. Открытые технические вопросы

1. Есть ли у пользователя NVIDIA GPU — предложено проверить `nvidia-smi`, ответа не было (влияет только на скорость локальных эмбеддингов; критично лишь для vLLM на сервере).
2. Где будет размещаться vLLM (свой GPU-сервер / аренда / облако) — не решено.
3. Статус первого PR (ML-скелет) и коммита пакета передачи — не подтверждён пользователем.
4. Контракт v0.1 ожидает ревью бекенда — возможны правки до стыковки (правило: изменения контракта — через PR ml+backend).
5. Параметры чанкинга (500/50) не тюнились — решать после реранкера и eval.
6. Момент внедрения `X-API-Key` и перехода на серверный Qdrant — согласовать в v0.2.
7. Унификация payload (`doc_id` есть только в `service.py`, нет в CLI `ingest.py`) — см. §7.12.
