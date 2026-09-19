FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN groupadd --system railplan && useradd --system --gid railplan --home /app railplan
WORKDIR /app

COPY pyproject.toml ./
COPY app ./app
COPY migrations ./migrations
COPY sql ./sql
COPY data ./data
COPY alembic.ini ./
COPY docker-entrypoint.sh ./
RUN pip install . && chmod 0555 docker-entrypoint.sh && chown -R railplan:railplan /app

USER railplan
EXPOSE 8000
HEALTHCHECK --interval=20s --timeout=5s --start-period=20s --retries=5 \
  CMD python -c "import os,urllib.request; port=os.getenv('PORT',os.getenv('RAILPLAN_PORT','8000')); urllib.request.urlopen(f'http://127.0.0.1:{port}/health/ready',timeout=3)"

ENTRYPOINT ["./docker-entrypoint.sh"]
