FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
# torch: CPU-сборка (образ в ~4 раза меньше; эмбеддинги считаем на CPU, GPU — только у vLLM).
# Ставим ДО requirements, чтобы pip не тянул тяжёлую CUDA-сборку как зависимость.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8001
# Без --workers: локальный Qdrant рассчитан на один процесс
CMD ["uvicorn", "service:app", "--host", "0.0.0.0", "--port", "8001"]
