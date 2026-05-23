FROM python:3.11-slim

WORKDIR /app

COPY . .

RUN pip install uv

RUN uv sync

EXPOSE 10000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "10000"]