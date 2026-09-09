#!/bin/bash
set -euo pipefail

usage() {
    printf '%s\n' \
        'Usage:' \
        '  vps_deploy.sh --help' \
        '  vps_deploy.sh --confirm-vps [--install-site /ABSOLUTE/RENDERED_CONF]'
}

case "${1:-}" in
    --help)
        usage
        exit 0
        ;;
    --confirm-vps)
        shift
        ;;
    *)
        usage >&2
        exit 2
        ;;
esac

site_candidate=''
while (( $# > 0 )); do
    case "$1" in
        --install-site)
            if [[ -n "$site_candidate" || $# -lt 2 || "$2" != /* ]]; then
                usage >&2
                exit 2
            fi
            site_candidate=$2
            shift 2
            ;;
        *)
            usage >&2
            exit 2
            ;;
    esac
done

if (( $(id -u) != 0 )); then
    printf '%s\n' 'vps_deploy.sh must run as root after explicit VPS confirmation.' >&2
    exit 1
fi

exec 9>/run/lock/libretiles-deploy.lock
if ! flock -n 9; then
    printf '%s\n' 'Another Libre Tiles deployment holds the deployment lock.' >&2
    exit 1
fi

SCRIPT_DIR=${BASH_SOURCE[0]%/*}
PROJECT_ROOT=$(cd -- "$SCRIPT_DIR/../.." && pwd -P)
case "$PROJECT_ROOT" in
    /home|/home/*)
        printf '%s\n' 'PROJECT_ROOT under /home is incompatible with ProtectHome=true.' >&2
        exit 1
        ;;
esac

BACKEND_UNIT=libretiles-backend.service
FRONTEND_UNIT=libretiles-frontend.service
SITE_TARGET=/etc/nginx/sites-available/libretiles.conf
SITE_ENABLED=/etc/nginx/sites-enabled/libretiles.conf
site_pending=0
apps_in_maintenance=0
target_existed=0
enabled_existed=0
SITE_TMP="${SITE_TARGET}.new.$$"
TARGET_BACKUP="${SITE_TARGET}.backup.$$"
LINK_TMP="${SITE_ENABLED}.new.$$"
ENABLED_BACKUP="${SITE_ENABLED}.backup.$$"

restore_site() {
    set +e
    rm -f -- "$SITE_TMP" "$LINK_TMP"
    if (( target_existed )); then
        rm -f -- "$SITE_TARGET"
        mv -f -- "$TARGET_BACKUP" "$SITE_TARGET"
    else
        rm -f -- "$SITE_TARGET" "$TARGET_BACKUP"
    fi
    if (( enabled_existed )); then
        rm -f -- "$SITE_ENABLED"
        mv -f -- "$ENABLED_BACKUP" "$SITE_ENABLED"
    else
        rm -f -- "$SITE_ENABLED" "$ENABLED_BACKUP"
    fi
    set -e
}

finish() {
    local status=$?
    trap - EXIT
    if (( site_pending )); then
        restore_site
    else
        rm -f -- "$SITE_TMP" "$TARGET_BACKUP" "$LINK_TMP" "$ENABLED_BACKUP"
    fi
    if (( status != 0 && apps_in_maintenance && ! site_pending )); then
        systemctl stop "$FRONTEND_UNIT" "$BACKEND_UNIT" >/dev/null 2>&1 || true
        printf '%s\n' 'Deployment failed; application services remain stopped.' >&2
    elif (( status != 0 && site_pending )); then
        printf '%s\n' 'Nginx site update failed; the prior site was restored.' >&2
    fi
    exit "$status"
}
trap finish EXIT

if ! id libretiles >/dev/null 2>&1; then
    printf '%s\n' 'The pre-created libretiles service account is required.' >&2
    exit 1
fi
for unit_path in \
    "/etc/systemd/system/$BACKEND_UNIT" \
    "/etc/systemd/system/$FRONTEND_UNIT"; do
    if [[ ! -f "$unit_path" ]]; then
        printf 'Required installed unit is missing: %s\n' "$unit_path" >&2
        exit 1
    fi
done

if [[ -n "$site_candidate" && ! -f "$site_candidate" ]]; then
    printf 'Rendered nginx candidate is missing: %s\n' "$site_candidate" >&2
    exit 1
fi

"$PROJECT_ROOT/backend/scripts/vps_preflight.sh"

for env_path in "$PROJECT_ROOT/backend/.env" "$PROJECT_ROOT/frontend/.env.local"; do
    if [[ ! -f "$env_path" ]]; then
        printf 'Required environment file is missing: %s\n' "$env_path" >&2
        exit 1
    fi
done
if [[ ! -f "$PROJECT_ROOT/backend/scripts/nginx/libretiles.conf" ]]; then
    printf '%s\n' 'The repository nginx template is missing.' >&2
    exit 1
fi
if [[ ! -e "$SITE_ENABLED" && ! -L "$SITE_ENABLED" ]]; then
    printf '%s\n' 'Install and verify the stripping nginx site before deployment.' >&2
    exit 1
fi
nginx -t

systemctl stop "$FRONTEND_UNIT"
systemctl stop "$BACKEND_UNIT"
apps_in_maintenance=1

VENV="$PROJECT_ROOT/backend/.venv"
if [[ ! -x "$VENV/bin/python" ]]; then
    if [[ -e "$VENV" ]]; then
        printf '%s\n' 'Existing backend/.venv is incomplete; refusing to replace it.' >&2
        exit 1
    fi
    runuser -u libretiles -- python3.12 -m venv "$VENV"
fi
if ! "$VENV/bin/python" -c 'import sys; raise SystemExit(sys.version_info[:2] != (3, 12))'; then
    printf '%s\n' 'Existing backend/.venv must use Python 3.12.' >&2
    exit 1
fi

run_in_dir() {
    local working_directory=$1
    shift
    runuser -u libretiles -- /bin/bash -c 'cd -- "$1"; shift; exec "$@"' \
        libretiles-run "$working_directory" "$@"
}

run_in_dir "$PROJECT_ROOT/backend" /usr/bin/env \
    "VIRTUAL_ENV=$VENV" POETRY_VIRTUALENVS_CREATE=false \
    poetry install --only main --no-root
run_in_dir "$PROJECT_ROOT/frontend" npm ci --include=dev
run_in_dir "$PROJECT_ROOT/frontend" npm run build
if ! run_in_dir "$PROJECT_ROOT/frontend" test -f .next/standalone/server.js; then
    printf '%s\n' 'Standalone frontend server is missing; deployment stopped.' >&2
    exit 1
fi

run_in_dir "$PROJECT_ROOT/frontend" test -d public
run_in_dir "$PROJECT_ROOT/frontend" test -d .next/static
run_in_dir "$PROJECT_ROOT/frontend" mkdir -p \
    .next/standalone/public .next/standalone/.next/static
run_in_dir "$PROJECT_ROOT/frontend" cp -a -- \
    public/. .next/standalone/public/
run_in_dir "$PROJECT_ROOT/frontend" cp -a -- \
    .next/static/. .next/standalone/.next/static/

run_in_dir "$PROJECT_ROOT/backend" "$VENV/bin/python" manage.py check
run_in_dir "$PROJECT_ROOT/backend" "$VENV/bin/python" manage.py migrate --noinput
run_in_dir "$PROJECT_ROOT/backend" "$VENV/bin/python" manage.py seed_models
run_in_dir "$PROJECT_ROOT/backend" "$VENV/bin/python" manage.py collectstatic --noinput

systemctl restart "$BACKEND_UNIT"
systemctl restart "$FRONTEND_UNIT"
systemctl is-active --quiet "$BACKEND_UNIT"
systemctl is-active --quiet "$FRONTEND_UNIT"

if [[ -n "$site_candidate" ]]; then
    if [[ -e "$SITE_TARGET" || -L "$SITE_TARGET" ]]; then
        cp -a -- "$SITE_TARGET" "$TARGET_BACKUP"
        target_existed=1
    fi
    if [[ -e "$SITE_ENABLED" || -L "$SITE_ENABLED" ]]; then
        cp -a -- "$SITE_ENABLED" "$ENABLED_BACKUP"
        enabled_existed=1
    fi
    site_pending=1
    install -m 0644 -o root -g root -- "$site_candidate" "$SITE_TMP"
    mv -Tf -- "$SITE_TMP" "$SITE_TARGET"
    ln -s -- "$SITE_TARGET" "$LINK_TMP"
    mv -Tf -- "$LINK_TMP" "$SITE_ENABLED"
    nginx -t
    systemctl reload nginx
    site_pending=0
    rm -f -- "$TARGET_BACKUP" "$ENABLED_BACKUP"
fi

apps_in_maintenance=0
printf '%s\n' 'Libre Tiles deployment completed.'
