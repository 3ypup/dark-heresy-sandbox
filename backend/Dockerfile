FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# pydantic<2 — чтобы использовать классический orm_mode,
# fastapi[standard] — включает uvicorn и полезные зависимости
RUN pip install --no-cache-dir "fastapi[standard]" "pydantic<2" sqlalchemy httpx

COPY app ./app

WORKDIR /app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

