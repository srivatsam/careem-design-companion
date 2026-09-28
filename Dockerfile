# Perfume recommendation MVP: FastAPI + SQLite.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8000 \
    DATABASE_PATH=/data/app.db \
    DEFAULT_LANG=en \
    RATE_LIMIT_PER_MINUTE=30

WORKDIR /app

# Non-root runtime user. uid/gid 1000 matches the Azure Files SMB mount defaults.
RUN groupadd --system --gid 1000 app \
 && useradd --system --uid 1000 --gid app --home-dir /app --shell /usr/sbin/nologin app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app/ ./app/
COPY data/seed/ ./data/seed/
# data/raw may hold only .gitkeep (or nothing); the entrypoint imports any *.csv found here.
COPY data/raw/ ./data/raw/
COPY scripts/ ./scripts/

RUN chmod +x scripts/*.sh \
 && mkdir -p /data \
 && chown -R app:app /data /app/data

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=600s --retries=3 \
  CMD python -c "import os,urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:%s/api/health' % os.environ.get('PORT','8000'), timeout=4); sys.exit(0)" || exit 1

ENTRYPOINT ["/app/scripts/entrypoint.sh"]
