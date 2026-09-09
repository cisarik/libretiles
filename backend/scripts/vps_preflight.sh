#!/bin/bash
set -euo pipefail

usage() {
    printf '%s\n' \
        'Usage: vps_preflight.sh [--help]' \
        'Checks Libre Tiles VPS prerequisites without changing the host.'
}

if [[ "${1:-}" == "--help" ]]; then
    usage
    exit 0
fi
if (( $# != 0 )); then
    usage >&2
    exit 2
fi

failures=0

pass() {
    printf 'PASS: %s\n' "$1"
}

fail() {
    printf 'FAIL: %s\n' "$1" >&2
    failures=$((failures + 1))
}

require_command() {
    local command_name=$1
    if command -v "$command_name" >/dev/null 2>&1; then
        pass "$command_name is installed"
    else
        fail "$command_name is required"
    fi
}

for command_name in python3.12 node npm poetry psql pg_isready redis-cli nginx systemctl runuser flock ufw; do
    require_command "$command_name"
done

if command -v python3.12 >/dev/null 2>&1; then
    if python3.12 -c 'import sys; raise SystemExit(sys.version_info[:2] != (3, 12))'; then
        pass 'Python 3.12 is compatible'
    else
        fail 'python3.12 does not report Python 3.12'
    fi
    if python3.12 -m venv --help >/dev/null 2>&1; then
        pass 'Python venv support is available'
    else
        fail 'Python 3.12 venv support is unavailable'
    fi
fi

if command -v node >/dev/null 2>&1; then
    node_version=$(node --version 2>/dev/null || true)
    if [[ "$node_version" =~ ^v([0-9]+)\.([0-9]+)\.([0-9]+) ]]; then
        node_major=${BASH_REMATCH[1]}
        node_minor=${BASH_REMATCH[2]}
        if (( (node_major == 20 && node_minor >= 19) ||
              (node_major == 22 && node_minor >= 12) ||
              node_major >= 24 )); then
            pass "Node ${node_version} is compatible (Node 24 is recommended)"
        else
            fail "Node ${node_version} is unsupported; require 20.19+, 22.12+, or 24+"
        fi
    else
        fail 'Unable to parse the Node version'
    fi
fi

if command -v poetry >/dev/null 2>&1; then
    poetry_version=$(poetry --version 2>/dev/null || true)
    if [[ "$poetry_version" =~ ([0-9]+)\.([0-9]+)\.([0-9]+) ]]; then
        poetry_major=${BASH_REMATCH[1]}
        poetry_minor=${BASH_REMATCH[2]}
        poetry_patch=${BASH_REMATCH[3]}
        if (( poetry_major == 2 &&
              (poetry_minor > 3 || (poetry_minor == 3 && poetry_patch >= 2)) )); then
            pass "${poetry_version} is compatible"
        else
            fail "${poetry_version} is unsupported; require Poetry 2.x >= 2.3.2"
        fi
    else
        fail 'Unable to parse the Poetry version'
    fi
fi

for service_name in postgresql.service redis-server.service; do
    if command -v systemctl >/dev/null 2>&1; then
        if systemctl is-active --quiet "$service_name"; then
            pass "$service_name is active"
        else
            fail "$service_name is not active"
        fi
    fi
done

if command -v ufw >/dev/null 2>&1; then
    if ufw status >/dev/null 2>&1; then
        pass 'UFW status is inspectable'
    else
        fail 'UFW status could not be inspected without privilege escalation'
    fi
fi

if (( failures > 0 )); then
    printf 'Preflight failed with %d issue(s).\n' "$failures" >&2
    exit 1
fi

printf '%s\n' 'Preflight passed.'
