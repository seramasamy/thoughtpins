FROM node:22-alpine@sha256:16e22a550f3863206a3f701448c45f7912c6896a62de43add43bb9c86130c3e2 AS web

WORKDIR /web

ARG VITE_GOOGLE_CLIENT_ID=""
ARG VITE_APPLE_CLIENT_ID=""
ENV VITE_GOOGLE_CLIENT_ID=$VITE_GOOGLE_CLIENT_ID
ENV VITE_APPLE_CLIENT_ID=$VITE_APPLE_CLIENT_ID

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/index.html frontend/tsconfig.json frontend/tsconfig.node.json frontend/vite.config.ts ./
COPY frontend/src ./src
COPY frontend/public ./public
COPY frontend/scripts/build.mjs ./scripts/build.mjs
RUN npm run build


FROM python:3.14-slim@sha256:cea0e6040540fb2b965b6e7fb5ffa00871e632eef63719f0ea54bca189ce14a6

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements-prod.lock ./
RUN pip install --no-cache-dir --require-hashes -r requirements-prod.lock

COPY pyproject.toml README.md LICENSE NOTICE ./
COPY src ./src
COPY --from=web /web/dist ./frontend/dist
COPY frontend/static ./frontend/static
COPY alembic.ini ./alembic.ini
COPY alembic ./alembic
COPY scripts ./scripts
COPY site ./site

RUN groupadd --gid 10001 thoughtpins \
    && useradd --uid 10001 --gid thoughtpins --create-home --shell /usr/sbin/nologin thoughtpins \
    && mkdir -p /app/data/qdrant /app/vault /app/reports \
    && chown -R thoughtpins:thoughtpins /app

USER 10001:10001

EXPOSE 8420 8421

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8420/health', timeout=3).read()"

CMD ["python", "-m", "thoughtpins.server", "--api-only"]
