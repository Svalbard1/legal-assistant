import httpx

from app.config import settings


class MLClient:
    def __init__(self):
        self.base_url = settings.ML_SERVICE_URL
        self.timeout = httpx.Timeout(
            90.0,
            connect=5.0,
        )

    async def ask(self, question: str, top_k: int = 3) -> dict:
        async with httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
        ) as client:
            response = await client.post(
                "/ask",
                json={
                    "question": question,
                    "top_k": top_k,
                },
            )

            response.raise_for_status()
            return response.json()


ml_client = MLClient()
