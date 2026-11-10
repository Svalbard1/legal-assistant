from fastapi import FastAPI

from app.schemas import AskRequest, AskResponse, Source


app = FastAPI(
    title="Legal Assistant Backend",
    version="0.1.0",
)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/ask", response_model=AskResponse)
async def ask(request: AskRequest):
    return AskResponse(
        answer=f"Тестовый ответ на вопрос: {request.question}",
        sources=[
            Source(
                file="mock_document.pdf",
                text="Это временный тестовый фрагмент документа.",
                score=0.95,
            )
        ],
        took_ms=10,
        llm="mock",
    )
