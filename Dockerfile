FROM python:3.11-slim

# Security: run as non-root
RUN addgroup --system app && adduser --system --ingroup app app

WORKDIR /app

# Install dependencies in a separate layer (cache-friendly)
COPY pyproject.toml .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

COPY app/ app/

USER app

EXPOSE 8080

# Single worker — Cloud Run scales horizontally via instances, not threads
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
