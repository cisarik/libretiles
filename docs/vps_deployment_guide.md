# VPS Deployment Guide

This runbook describes an operator-owned production deployment on an Ubuntu-style systemd VPS. The repository supplies reviewed templates; it does not install packages, configure a firewall, obtain certificates, open SSH access, or operate a host automatically. Run the commands only on the intended VPS under separate production authority.

## Topology And Prerequisites

Use `/srv/libretiles` as the default installation root and a pre-created, non-login `libretiles` service account. The public nginx listener exposes only ports 80 and 443. All application listeners are loopback-only:

| Listener | Purpose |
|---|---|
| `127.0.0.1:3000` | Next.js UI and frontend API routes |
| `127.0.0.1:8000` | Daphne/Django HTTP and websocket upstream |
| `127.0.0.1:8001` | nginx callback from Next.js to Django |
| `127.0.0.1:8443` | private TLS Django contrib admin |

PostgreSQL and Redis also remain private. The deployment expects Python 3.12 with venv support, Poetry 2.x version 2.3.2 or newer, Node 20.19+, 22.12+, or 24+ (Node 24 is the documented default), npm, PostgreSQL and Redis tools and active services, nginx, systemd, `runuser`, `flock`, and UFW status visibility. Keep the repository and runtime state outside `/home`; the units use `ProtectHome=true`.

Prepare DNS, certificates, host packages, firewall policy, the service account, `/srv/libretiles` ownership, and SSH access separately. Permit public inbound traffic only on 80 and 443. A deployment stops the frontend and backend and therefore requires a maintenance window.

## Recovery Preparation

Before deployment, create and verify a PostgreSQL backup and retain recoverable copies of the previous application commit, dependency state, frontend build, rendered nginx site, systemd units, and environment files. Test the restoration process independently. A code revert does not automatically reverse a database schema change; review every migration before choosing a schema rollback.

The deployment script leaves application services stopped after a failed deployment. Restore the known-good code, dependencies, build, and configuration only after assessing whether migrations committed durable changes. Do not blindly restart old code against a partially migrated database.

## Environment Files

Create `backend/.env` and `frontend/.env.local` privately on the VPS, owned and readable only as required by the `libretiles` service. Do not commit, source, print, or copy credential values into command output. Use literal assignments compatible with Django and Next.js.

Required production-facing names include:

| Process | Variables and requirements |
|---|---|
| Django security | Set `DJANGO_SECRET_KEY` privately, `DJANGO_DEBUG=false`, and `DJANGO_ALLOWED_HOSTS=YOUR_DOMAIN`. |
| Browser origins | Set `CORS_ALLOWED_ORIGINS=https://YOUR_DOMAIN` and `DJANGO_CSRF_TRUSTED_ORIGINS=https://YOUR_DOMAIN`. |
| Proxy trust | Set `DJANGO_NUM_PROXIES=1`. Set `DJANGO_SECURE_PROXY_SSL_HEADER=true` only after the supplied stripping nginx configuration is rendered, installed, and validated. |
| PostgreSQL | Set `DB_ENGINE=postgresql` plus `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, and `DB_PORT`. Review optional `DB_CONN_MAX_AGE` and connection-health settings for the local service. |
| Redis | Set `REDIS_URL` for Channels and `DJANGO_THROTTLE_CACHE_URL` for shared throttling. When the latter is absent, production uses `REDIS_URL` as its fallback. |
| Catalog and reset controls | Keep `DYNAMIC_FREE_MODEL_CATALOG_ENABLED=false` and `ALLOW_DESTRUCTIVE_GAME_STATE_RESET=false` unless a separately reviewed operation changes them. |
| Next origins | Set `NEXT_PUBLIC_API_URL=https://YOUR_DOMAIN` and `BACKEND_URL=http://127.0.0.1:8001`. Do not point `BACKEND_URL` directly at Daphne on port 8000: production HTTPS redirects and canonical host validation require the callback listener's overwritten headers. |
| Next providers | Configure only the server-side credential names needed from `frontend/.env.local.example`, including `GROQ_API_KEY`, `GEMINI_API_KEY`, `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `MISTRAL_API_KEY`, `IBM_CLOUD_API_KEY`, `IBM_WATSONX_PROJECT_ID`, `IBM_WATSONX_REGION`, `AION_API_KEY`, `HF_TOKEN`, `OPENROUTER_API_KEY`, and `NVIDIA_API_KEY`. Never use `NEXT_PUBLIC_` for credentials or copy provider credentials into Django. |

`NEXT_PUBLIC_API_URL` is embedded during the frontend build, while server-only values are consumed by the running process. A pre-existing dotenv file overrides code defaults and is loaded at process start. After changing backend variables, restart the backend; after changing a build-time public variable, rebuild and restart the frontend. Remove or reconcile conflicting dotenv files rather than depending on load order.

The stripping proxy is a security prerequisite for proxy SSL trust. Its proxy locations overwrite forwarded host, protocol, port, and client-address headers instead of trusting inbound forwarding headers. Do not enable `DJANGO_SECURE_PROXY_SSL_HEADER` before that exact behavior is installed. `DJANGO_NUM_PROXIES=1` lets DRF derive the public client identity through the one nginx hop. It does not change django-axes socket-peer handling; Next-to-Django callback traffic also originates from loopback.

## Render Nginx And Systemd

`backend/scripts/nginx/libretiles.conf` is an nginx `http`-context snippet, not a replacement for `/etc/nginx/nginx.conf`. Render `YOUR_DOMAIN`, `PROJECT_ROOT`, `CERTIFICATE_PATH`, and `CERTIFICATE_KEY_PATH` outside Git. Obtain certificates separately. Review that 80/443 are public and that 8001/8443 contain explicit `127.0.0.1` binds before installing the site. Test the complete nginx configuration before reload. Only after this stripping proxy is installed and validated should the operator enable `DJANGO_SECURE_PROXY_SSL_HEADER=true` and restart Django.

Render `PROJECT_ROOT` in both files under `backend/scripts/systemd/`, install them as `libretiles-backend.service` and `libretiles-frontend.service`, then reload the systemd manager. The units require their environment files and run as `libretiles`; they do not migrate, seed, install, or build. Enable the units for future boots only after rendering and review, without prematurely starting unbuilt services.

The repository commands below illustrate the intended later host sequence; adjust only paths already rendered for that host:

```bash
PROJECT_ROOT/backend/scripts/vps_preflight.sh
PROJECT_ROOT/backend/scripts/vps_deploy.sh --confirm-vps
```

Preflight is read-only and fails when requirements or service/UFW status cannot be verified. Deployment acquires a host lock, verifies existing nginx and required files, stops frontend then backend, performs locked dependency installs and the frontend build as `libretiles`, checks and migrates Django, seeds catalog rows without changing existing activation, collects static files, and starts backend then frontend.

To replace the nginx site as part of that deployment, supply an absolute path to an operator-rendered candidate:

```bash
PROJECT_ROOT/backend/scripts/vps_deploy.sh --confirm-vps \
  --install-site /ABSOLUTE/RENDERED_CONF
```

That option installs the site atomically, restores the previous site when `nginx -t` fails, and reloads nginx only after both applications start successfully. Without `--install-site`, deployment does not replace or reload nginx. The script does not create users, install OS packages, write environment files, configure UFW, obtain certificates, change Git, install schedules, run catalog synchronization, or call providers.

## Operational Checks

Perform these checks after deployment under host authority; this repository implementation does not execute them:

- Confirm port 80 redirects to canonical `https://YOUR_DOMAIN`, the landing page works, and catalog, `/api/models`, and `/api/prompts` return through their intended upstreams.
- Request `/api/auth/me/` without credentials and confirm an authentication failure rather than an HTTP-to-HTTPS callback redirect.
- Confirm public `/admin` shows the Next staff console and no public path reaches Django contrib admin.
- Confirm unauthenticated staff API requests fail before any provider activity.
- Start a separately authorized multiplayer session and inspect a fresh-ticket `wss://YOUR_DOMAIN/ws/game/...` request for a 101 upgrade.
- During a separately authorized game or simulation, confirm SSE events arrive incrementally rather than at response completion.
- Use socket and systemd status inspection to verify Next, Daphne, the callback, and private admin remain bound only to loopback and both application units are active.
- Inspect journald and the bounded nginx access logs for failures. The nginx log format omits query strings, credentials, cookies, and Referer, including websocket tickets.
- Monitor certificate expiry, PostgreSQL/Redis health, service restarts, disk capacity, and backup success.

These checks establish routing and readiness, not provider capability. Provider probes and games consume external quota and require separate authorization.

## Private Django Admin

Django contrib admin is available only through TLS on `127.0.0.1:8443`. From an authorized workstation, create an SSH local forward from local port 8443 to VPS `127.0.0.1:8443`, and temporarily resolve `YOUR_DOMAIN` to local loopback on that workstation. Browse to `https://YOUR_DOMAIN:8443/admin/` so TLS, secure cookies, Host, and CSRF all retain the canonical hostname and private port. Remove the temporary hostname mapping and close the tunnel when finished. Do not expose 8443 publicly or replace Django's existing authentication and CSRF controls.

## Catalog Operation Reminder

The optional OpenRouter catalog refresh remains a separately authorized production schedule, not part of deployment:

- Name: `libretiles-openrouter-catalog-refresh`
- Cadence: daily at 03:17 UTC
- Command: `PROJECT_ROOT/backend/.venv/bin/python manage.py sync_openrouter_models` under a non-overlapping platform lock

Do not install that schedule through these scripts. Review [the architecture guide](architecture.md) for catalog rollout and rollback details.
