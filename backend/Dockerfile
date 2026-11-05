FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

# System deps: libpq via psycopg[binary] wheels; nothing else needed
COPY requirements.txt requirements-models.txt ./
RUN pip install -r requirements.txt

# Optional: heavy model stack (torch + sentence-transformers) for real embeddings.
# Kept out of the default image; build with --build-arg INSTALL_MODELS=true
ARG INSTALL_MODELS=false
RUN if [ "$INSTALL_MODELS" = "true" ]; then pip install -r requirements-models.txt; fi

COPY . .

# Non-root user
RUN useradd -m appuser && chown -R appuser /srv
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
