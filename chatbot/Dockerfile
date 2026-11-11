FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TIKTOKEN_CACHE_DIR=/app/tokenizer-cache
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && python -c "import tiktoken; tiktoken.get_encoding('cl100k_base')"
COPY rag_app ./rag_app
COPY web ./web
COPY config ./config
COPY data ./data
RUN useradd --create-home appuser && mkdir -p /app/storage && chown -R appuser:appuser /app
USER appuser
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "rag_app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
