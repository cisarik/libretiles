FROM node:24.21.0-bookworm-slim@sha256:2fe369e969550cde8e867afc3fe370b260140cab4a23d467074295b42163d553 AS deps

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:24.21.0-bookworm-slim@sha256:2fe369e969550cde8e867afc3fe370b260140cab4a23d467074295b42163d553 AS builder

WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN npm run build \
    && cp -a public/. .next/standalone/public/ \
    && mkdir -p .next/standalone/.next/static \
    && cp -a .next/static/. .next/standalone/.next/static/

FROM node:24.21.0-bookworm-slim@sha256:2fe369e969550cde8e867afc3fe370b260140cab4a23d467074295b42163d553 AS runtime

ENV NODE_ENV=production \
    NODE_OPTIONS=--require=/opt/libretiles/load-secrets.cjs
RUN groupadd --gid 10003 libretiles \
    && useradd --uid 10003 --gid 10003 --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin libretiles \
    && mkdir -p /app/.next/cache /opt/libretiles \
    && chown -R 10003:10003 /app /opt/libretiles
WORKDIR /app
COPY --from=builder --chown=10003:10003 /app/.next/standalone ./
COPY --chown=10003:10003 docker/load-secrets.cjs /opt/libretiles/load-secrets.cjs
COPY --chown=10003:10003 docker/healthcheck.cjs /opt/libretiles/healthcheck.cjs
USER 10003:10003

ENTRYPOINT ["/usr/bin/env", "HOSTNAME=127.0.0.1", "PORT=3000", "node", "server.js"]
