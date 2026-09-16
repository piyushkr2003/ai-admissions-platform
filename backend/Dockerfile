FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic

RUN pip install --no-cache-dir .

RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status==200 else 1)"

# Invoked via `python -m <module>` rather than the bare `alembic`/`uvicorn`
# console scripts: this only requires the packages to be importable, so it
# can't fail with a "command not found" if a console-script entry point
# ever ends up outside the runtime PATH (e.g. a platform overriding the
# container's start command). Applies pending Alembic migrations before
# the server starts serving traffic; `exec` hands off PID 1 to uvicorn so
# it still receives SIGTERM directly for a clean shutdown.
CMD ["sh", "-c", "python -m alembic upgrade head && exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"]
