from fastapi import FastAPI, HTTPException
import httpx

from app.ml_client import ml_client
from app.schemas import AskRequest, AskResponse

app = FastAPI(
    title="Legal Assistant Backend",
    version="0.1.0",
)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/ask", response_model=AskResponse)
async def ask(request: AskRequest):
    try:
        result = await ml_client.ask(
            question=request.question,
            top_k=request.top_k,
            history=[
                message.model_dump()
                for message in request.history
            ],
        )
        return AskResponse(**result)

    except httpx.HTTPStatusError as exc:
        try:
            payload = exc.response.json()
            detail = (
                payload.get("detail", "ML service returned an error")
                if isinstance(payload, dict)
                else "ML service returned an error"
            )
        except ValueError:
            detail = "ML service returned an error"

        raise HTTPException(
            status_code=exc.response.status_code,
            detail=detail,
        )

    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="ML service timed out",
        )

    except httpx.RequestError:
        raise HTTPException(
            status_code=502,
            detail="ML service is unavailable",
        )
