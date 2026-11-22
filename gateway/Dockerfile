FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY gateway_app ./gateway_app
RUN useradd --create-home gateway
USER gateway
EXPOSE 8080
CMD ["python", "-m", "uvicorn", "gateway_app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
