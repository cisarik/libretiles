FROM python:3.12.14-slim-bookworm@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254 AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    VIRTUAL_ENV=/app/.venv
WORKDIR /build/backend
RUN python -m venv /app/.venv
RUN pip install poetry==2.3.2
COPY README.md /build/README.md
COPY backend/pyproject.toml backend/poetry.lock ./
RUN poetry install --only main --no-root --no-interaction --no-ansi

FROM python:3.12.14-slim-bookworm@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254 AS runtime

ENV PATH=/app/.venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
RUN groupadd --gid 10001 libretiles \
    && useradd --uid 10001 --gid 10001 --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin libretiles \
    && mkdir -p /app/backend/staticfiles /run/libretiles \
    && chown -R 10001:10001 /app /run/libretiles \
    && chmod 0770 /run/libretiles
WORKDIR /app/backend
COPY --from=builder --chown=10001:10001 /app/.venv /app/.venv
COPY --chown=10001:10001 backend/manage.py ./manage.py
COPY --chown=10001:10001 backend/config ./config
COPY --chown=10001:10001 backend/accounts ./accounts
COPY --chown=10001:10001 backend/catalog ./catalog
COPY --chown=10001:10001 backend/game ./game
COPY --chown=10001:10001 backend/gamecore ./gamecore
COPY --chown=10001:10001 backend/assets ./assets
COPY --chown=10001:10001 backend/docker ./docker
RUN chmod 0555 docker/start.sh docker/healthcheck.py
USER 10001:10001

CMD ["/app/backend/docker/start.sh", "serve"]
