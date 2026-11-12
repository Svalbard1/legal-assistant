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
        )

        return AskResponse(**result)

    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code

        if status_code == 422:
            raise HTTPException(
                status_code=422,
                detail="ML service rejected the request",
            )

        if status_code == 404:
            raise HTTPException(
                status_code=404,
                detail="No relevant documents found",
            )

        raise HTTPException(
            status_code=502,
            detail="ML service returned an error",
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
