# Dockerized VPS Deployment Guide

This is the sole Libre Tiles production deployment runbook. Production uses one
Docker Compose project; the root development scripts remain local-only. The
repository does not operate a host, issue a real certificate, configure DNS,
SSH, a firewall, backups, or schedules without separate production authority.

## Topology

Nginx is the only host-published service. PostgreSQL, Redis, Django, and Next do
not publish ports.

| Host listener | Purpose |
|---|---|
| Public `80` | ACME HTTP-01 and HTTPS redirect |
| Public `443` | Application TLS edge |
| `127.0.0.1:8443` | Private TLS Django contrib admin through an SSH tunnel |

Next and nginx are separate containers sharing nginx's network namespace. The
standalone server is forced to `HOSTNAME=127.0.0.1 PORT=3000`; nginx reaches it
on loopback. Next reaches Django through nginx's restricted callback at
`BACKEND_URL=http://127.0.0.1:8001`. Django listens only on the group-restricted
`/run/libretiles/backend.sock` Unix socket.

Nginx/Next have no PostgreSQL or Redis network membership. Backend uses isolated
database/cache networks. Certbot has a separate ACME-egress network and shares
only certificate, challenge, and reload-coordination volumes.

Nginx is the narrow container-root exception. Its PID-1 master runs as UID 0
with shared GID 10001 and exactly `NET_BIND_SERVICE`, `SETGID`, and `SETUID`;
this is not host-root authority. `SETGID` and `SETUID` exist solely so nginx can
drop request workers to `10002:10001`; those workers retain zero effective
capabilities. The master writes only its small `/run/nginx-master` tmpfs, while
five dedicated `/var/cache/nginx/*` tmpfs mounts are owned by the worker
identity. The shared group provides access to the backend socket, Certbot
marker, and certificate paths. Certbot normalizes certificate directories to
`0750` and the full chain and private key to `0640`; private keys are never
world-readable.

## Host Prerequisites

Prepare these separately on the intended VPS:

- Docker Engine with Compose plugin support for `network_mode: service:...`,
  health dependencies, secrets, profiles, `init`, and service sysctls.
- DNS for the operator-selected hostname pointing at the VPS.
- Public inbound TCP 80 and 443 only; keep 8443 host-loopback-only.
- SSH access, host patching, disk capacity monitoring, and encrypted off-host
  backup storage.
- A clone at the exact reviewed commit and enough storage to retain the prior
  images and database backup for rollback.

Do not deploy directly from an unreviewed dirty working tree.

## Configuration And Secrets

Create the non-secret selector file:

```bash
cp .env.docker.example .env.docker
chmod 0600 .env.docker
```

Replace every `example.invalid` and `replace-me` selector. `APP_VERSION` should
be the reviewed Git commit. Keep
`DYNAMIC_FREE_MODEL_CATALOG_ENABLED=false` for initial rollout.

Provision dedicated numeric secret-reader GID 10004 as a separate R5 host
operation, then create these gitignored sources as root-owned regular files with
GID 10004 and mode `0440` inside root-owned mode-`0700` `deploy/secrets/`.
Use a private editor or secret-delivery mechanism; never print, source, or pass
values as command arguments:

```text
deploy/secrets/django-secret-key
deploy/secrets/postgres-password
deploy/secrets/frontend-credentials.json
```

The Django file contains one strong key as specified by
`backend/.env.example`. The PostgreSQL file contains one password line. The
frontend file is one closed-key JSON object; `{}` intentionally permits UI boot
without an AI credential. See `deploy/secrets/README.md`. Never copy the
committed invalid placeholders into production. That README gives the complete
newbie-legible, temporary-file-plus-atomic-rename provisioning and rotation
procedure and numeric metadata checks.

Local file-backed Compose preserves host ownership and mode; it does not enforce
secret-target `uid`, `gid`, or `mode` declarations. The production Compose file
therefore gives supplemental GID 10004 only to postgres, backend-init, backend,
frontend, and db-tools. Explicit per-service mounts remain mandatory:
PostgreSQL/db-tools receive only the database password; backend/backend-init
receive the database password and Django key; frontend receives only its JSON.
Nginx, Redis, and Certbot receive neither the reader group nor these mounts.

Compose fails when selectors or secret files are missing. Rendered Compose
configuration contains secret paths, not values:

```bash
docker compose --env-file .env.docker --profile tls --profile ops config
```

Review the output before building: only nginx may have `ports`; private admin
must map from host `127.0.0.1`; frontend must use
`network_mode: service:nginx`; database/cache networks must be internal.
Also verify every secret source with metadata-only `stat`: each must be a regular
file ending in `0:10004 440`, while `deploy/secrets/` must end in
`0:0 700 directory`. Stop rather than weakening a file to world-readable.

## Build And First Start

Images use exact version tags plus immutable multi-architecture digests. Build
from the committed lockfiles:

```bash
docker compose --env-file .env.docker --profile tls --profile ops build
docker compose --env-file .env.docker up -d
docker compose --env-file .env.docker ps
```

`backend-init` checks Django, applies migrations, seeds catalog rows, and
collects static files before backend starts. A failure leaves backend stopped.
Redis is intentionally non-durable; PostgreSQL uses its named data volume.

Before a certificate exists, nginx serves only `/healthz` and
`/.well-known/acme-challenge/` over HTTP. Application traffic receives 503;
plaintext fallback is never enabled.

## TLS Bootstrap And Renewal

Real issuance contacts ACME and requires separate production authority. Verify
DNS and public port 80 first, then run exactly one issuance attempt:

```bash
docker compose --env-file .env.docker --profile tls run --rm certbot issue
docker compose --env-file .env.docker --profile tls up -d certbot
```

The committed `example.invalid` hostname and email are rejected. Issuance does
not retry automatically, avoiding an ACME rate-limit loop. On success Certbot
signals nginx through a shared marker; nginx renders the TLS configuration,
runs `nginx -t`, and reloads only after validation.

The long-running Certbot service checks renewal twice daily. Successful renewal
uses the same validated reload path. A failed renewal exits nonzero and retains
the current certificate. Monitor Certbot health and certificate expiry outside
the container; alerts and host scheduling are deployment/host-hardening work.

## Health And Exposure Checks

After startup verify, under production authority:

- All required services are healthy and `backend-init` exited zero.
- Port 80 redirects to the canonical hostname after TLS bootstrap.
- Public `/admin` is the Next staff console; public `/static/` is denied.
- Unmatched `/api/` paths return 404.
- `/api/catalog/models/` reaches Django and forged forwarding headers are
  overwritten by nginx.
- Websocket upgrades work and SSE events stream without proxy buffering.
- No host listener exists for 3000, 8000, 8001, 5432, or 6379.
- Nginx/Next do not belong to the PostgreSQL or Redis networks.
- Logs omit query strings, Authorization, cookies, Referer, bodies, and secrets.
- Nginx PID 1 is `0:10001` with exactly `NET_BIND_SERVICE`, `SETGID`, and
  `SETUID`; the identity-transition capabilities exist solely to drop every
  request worker to `10002:10001` with zero effective capabilities. Workers can
  write only the dedicated temp tmpfs paths.
- The backend socket, certificate files, and consumed reload marker demonstrate
  shared-GID access without `DAC_OVERRIDE` or `CHOWN`; the master's `SETUID` and
  `SETGID` are not used to bypass their group-only modes.

`scripts/validate_docker_deployment.sh` performs the corresponding synthetic
local checks and a disposable restore rehearsal without contacting ACME or an
AI provider.

## Updates And Namespace Coupling

Nginx owns the network namespace used by frontend. A certificate/configuration
reload is safe, but recreating nginx alone can strand frontend in the old
namespace. Never use nginx-only `--force-recreate`, `up --no-deps nginx`, or an
equivalent replacement.

Before every update, create and verify a backup. Change `APP_VERSION` to the new
reviewed commit, build all affected images, and recreate nginx and frontend
together whenever either image or their Compose/network configuration changes:

```bash
docker compose --env-file .env.docker --profile tls --profile ops build
docker compose --env-file .env.docker up -d --force-recreate nginx frontend
docker compose --env-file .env.docker up -d
docker compose --env-file .env.docker ps
```

Verify both containers share one network namespace and repeat route/exposure
checks. Compose `restart` does not restart dependants and is not a substitute
for paired recreation.

## Backup And Restore Rehearsal

Create a custom-format logical backup with a safe unique basename:

```bash
docker compose --env-file .env.docker --profile ops run --rm \
  db-tools backup backup-YYYYMMDDTHHMMSSZ.dump
docker compose --env-file .env.docker --profile ops run --rm \
  db-tools verify backup-YYYYMMDDTHHMMSSZ.dump
```

The tool rejects paths, symlinks, existing destinations, unsafe names, and
unverified archives. Dumps use `--no-owner --no-acl`, are written atomically,
and end mode `0600` in the named backup volume.

Treat dumps as sensitive. Retain a verified backup before each deployment,
seven daily copies, and four weekly copies. Export each to approved encrypted
off-host storage. The local backup volume is not an adequate sole copy.

Restore is deliberately limited to an explicitly disposable, empty database on
a host name different from the source. Run the repository validation script for
the routine rehearsal. A real recovery must create a new PostgreSQL data volume,
restore and validate there, stop application writes, then change
`POSTGRES_DATA_VOLUME`; never overwrite the source volume or run an older
PostgreSQL major against a newer data directory.

## Rollback

Retain the previous Compose source, exact images, and pre-update backup. For a
code-only rollback, restore prior image selectors only after confirming schema
compatibility. If schema/data is incompatible, restore the verified dump into a
new volume and validate it before switching the configured volume name. Never
blindly run old code against a partially migrated database.

Do not keep systemd or host nginx running as a parallel deployment. Re-enabling
a superseded owner is a separate rollback decision requiring host authority and
database compatibility evidence.

## Private Django Admin

Create an SSH local forward from workstation port 8443 to VPS
`127.0.0.1:8443`. Temporarily resolve the production hostname to local loopback
on that workstation, then browse to:

```text
https://YOUR_DOMAIN:8443/admin/
```

Using the canonical hostname preserves TLS, secure cookies, Host validation,
and CSRF. Close the tunnel and remove the temporary mapping afterward. Never
publish host port 8443 on a non-loopback address.

## Monitoring And Deferred Host Work

Monitor service health/restarts, certificate expiry and renewal, PostgreSQL
backup success, restore rehearsals, disk/inode capacity, Docker storage growth,
and application errors. Host firewall, SSH hardening, Docker daemon access,
patching, disk encryption, external alerts, resource sizing, and off-host
backup credentials require a separate R5 host audit.

The optional OpenRouter catalog refresh remains separately authorized and is
not installed by Compose:

- Name: `libretiles-openrouter-catalog-refresh`
- Cadence: daily at 03:17 UTC
- Command: `python manage.py sync_openrouter_models` under a non-overlapping lock

Provider probes, games, catalog synchronization, real ACME calls, and all live
host changes remain outside repository-only implementation and validation.
