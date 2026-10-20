FROM python:3.12.8-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    CHROME_DEVEL_SANDBOX=/usr/local/sbin/chrome-devel-sandbox

WORKDIR /app

COPY requirements.lock ./
RUN pip install --no-cache-dir --requirement requirements.lock
RUN python -m playwright install --with-deps --no-shell chromium
RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin app \
    && chmod -R a+rX /ms-playwright \
    && sandbox_path="$(find /ms-playwright -type f -name chrome_sandbox -print -quit)" \
    && test -n "$sandbox_path" \
    && install --owner=root --group=root --mode=4755 "$sandbox_path" "$CHROME_DEVEL_SANDBOX"

COPY app ./app

USER 10001:10001
EXPOSE 8000

CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
