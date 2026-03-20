#!/usr/bin/env bash
# Libre Tiles dev supervisor
# Usage:
#   ./scripts/libretiles.sh start
#   ./scripts/libretiles.sh stop
#   ./scripts/libretiles.sh restart
#   ./scripts/libretiles.sh status
#   ./scripts/libretiles.sh logs
#
# Default command is "start". Services run detached and are managed via pid/log
# files under ./.dev/.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
STATE_DIR="$ROOT_DIR/.dev"
RUN_DIR="$STATE_DIR/run"
LOG_DIR="$STATE_DIR/logs"

BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
BACKEND_PORT=8000
FRONTEND_PORT=3000

BACKEND_PID_FILE="$RUN_DIR/backend.pid"
FRONTEND_PID_FILE="$RUN_DIR/frontend.pid"
BACKEND_LOG_FILE="$LOG_DIR/backend.log"
FRONTEND_LOG_FILE="$LOG_DIR/frontend.log"

COMMAND="${1:-start}"

ensure_state_dirs() {
    mkdir -p "$RUN_DIR" "$LOG_DIR"
}

usage() {
    cat <<'EOF'
Libre Tiles dev supervisor

Usage:
  ./scripts/libretiles.sh [start|stop|restart|status|logs]

Commands:
  start    Start backend and frontend in detached dev mode
  stop     Stop managed Libre Tiles dev services
  restart  Stop then start services again
  status   Show current service state
  logs     Follow backend/frontend logs

Shortcuts:
  ./scripts/reload.sh    Same as: ./scripts/libretiles.sh restart
EOF
}

service_dir() {
    case "$1" in
        backend) printf '%s\n' "$BACKEND_DIR" ;;
        frontend) printf '%s\n' "$FRONTEND_DIR" ;;
        *) return 1 ;;
    esac
}

service_port() {
    case "$1" in
        backend) printf '%s\n' "$BACKEND_PORT" ;;
        frontend) printf '%s\n' "$FRONTEND_PORT" ;;
        *) return 1 ;;
    esac
}

service_pid_file() {
    case "$1" in
        backend) printf '%s\n' "$BACKEND_PID_FILE" ;;
        frontend) printf '%s\n' "$FRONTEND_PID_FILE" ;;
        *) return 1 ;;
    esac
}

service_log_file() {
    case "$1" in
        backend) printf '%s\n' "$BACKEND_LOG_FILE" ;;
        frontend) printf '%s\n' "$FRONTEND_LOG_FILE" ;;
        *) return 1 ;;
    esac
}

service_name() {
    case "$1" in
        backend) printf '%s\n' "backend" ;;
        frontend) printf '%s\n' "frontend" ;;
        *) return 1 ;;
    esac
}

service_url() {
    case "$1" in
        backend) printf '%s\n' "http://localhost:$BACKEND_PORT" ;;
        frontend) printf '%s\n' "http://localhost:$FRONTEND_PORT" ;;
        *) return 1 ;;
    esac
}

is_pid_running() {
    local pid="$1"
    kill -0 "$pid" 2>/dev/null
}

pid_cmd() {
    ps -p "$1" -o args= 2>/dev/null || true
}

pid_cwd() {
    readlink -f "/proc/$1/cwd" 2>/dev/null || true
}

pid_pgid() {
    ps -p "$1" -o pgid= 2>/dev/null | tr -d ' ' || true
}

service_is_owned_pid() {
    local service="$1"
    local pid="$2"
    local expected_dir actual_dir cmd

    expected_dir="$(service_dir "$service")"
    actual_dir="$(pid_cwd "$pid")"
    cmd="$(pid_cmd "$pid")"

    if [ -z "$actual_dir" ] || [ "$actual_dir" != "$expected_dir" ]; then
        return 1
    fi

    case "$service" in
        backend)
            [[ "$cmd" == *"manage.py runserver"* || "$cmd" == *"poetry run python"* ]]
            ;;
        frontend)
            [[ "$cmd" == *"npm run dev"* || "$cmd" == *"next-server"* || "$cmd" == *"next dev"* || "$cmd" == *"next/dist/bin/next"* ]]
            ;;
        *)
            return 1
            ;;
    esac
}

service_port_pids() {
    local port
    port="$(service_port "$1")"
    fuser -n tcp "$port" 2>/dev/null | awk '{for (i = 1; i <= NF; i++) if ($i ~ /^[0-9]+$/) print $i}'
}

service_owned_port_pids() {
    local service="$1"
    local pid

    while read -r pid; do
        [ -n "$pid" ] || continue
        if service_is_owned_pid "$service" "$pid"; then
            printf '%s\n' "$pid"
        fi
    done < <(service_port_pids "$service")
}

service_foreign_port_pids() {
    local service="$1"
    local pid

    while read -r pid; do
        [ -n "$pid" ] || continue
        if ! service_is_owned_pid "$service" "$pid"; then
            printf '%s\n' "$pid"
        fi
    done < <(service_port_pids "$service")
}

service_managed_pid() {
    local service="$1"
    local pid_file pid

    pid_file="$(service_pid_file "$service")"
    if [ ! -f "$pid_file" ]; then
        return 1
    fi

    pid="$(tr -d '[:space:]' < "$pid_file" 2>/dev/null || true)"
    if [ -z "$pid" ]; then
        return 1
    fi

    if is_pid_running "$pid" && service_is_owned_pid "$service" "$pid"; then
        printf '%s\n' "$pid"
        return 0
    fi

    return 1
}

cleanup_stale_pid_file() {
    local service="$1"
    local pid_file

    pid_file="$(service_pid_file "$service")"
    if [ -f "$pid_file" ] && ! service_managed_pid "$service" >/dev/null 2>&1; then
        rm -f "$pid_file"
    fi
}

adopt_service_if_running() {
    local service="$1"
    local pid pid_file

    pid_file="$(service_pid_file "$service")"
    cleanup_stale_pid_file "$service"

    if pid="$(service_managed_pid "$service" 2>/dev/null)"; then
        printf '%s\n' "$pid" > "$pid_file"
        return 0
    fi

    pid="$(service_owned_port_pids "$service" | head -n 1 || true)"
    if [ -n "$pid" ]; then
        printf '%s\n' "$pid" > "$pid_file"
        return 0
    fi

    return 1
}

print_service_conflict() {
    local service="$1"
    local pid cmd

    pid="$(service_foreign_port_pids "$service" | head -n 1 || true)"
    if [ -z "$pid" ]; then
        return 0
    fi

    cmd="$(pid_cmd "$pid")"
    echo "[$(service_name "$service")] Port $(service_port "$service") is already in use by pid $pid."
    if [ -n "$cmd" ]; then
        echo "[$(service_name "$service")] Command: $cmd"
    fi
    echo "[$(service_name "$service")] Stop that process or free the port before starting Libre Tiles."
}

ensure_backend_env() {
    if [ ! -f "$BACKEND_DIR/.env" ]; then
        cp "$BACKEND_DIR/.env.example" "$BACKEND_DIR/.env"
        echo "[backend] Created backend/.env from .env.example"
    fi
}

ensure_frontend_env() {
    if [ ! -f "$FRONTEND_DIR/.env.local" ]; then
        cp "$FRONTEND_DIR/.env.local.example" "$FRONTEND_DIR/.env.local"
        echo "[frontend] Created frontend/.env.local from .env.local.example"
    fi
}

prepare_backend() {
    ensure_backend_env
    echo "[backend] Preparing dependencies and database..."
    (
        cd "$BACKEND_DIR"
        poetry install --quiet
        poetry run python manage.py migrate --run-syncdb --verbosity 0
        poetry run python manage.py seed_models >/dev/null 2>&1 || true
    )
}

prepare_frontend() {
    ensure_frontend_env
    echo "[frontend] Preparing dependencies..."
    (
        cd "$FRONTEND_DIR"
        npm install --silent
    )
}

write_log_header() {
    local service="$1"
    local log_file

    log_file="$(service_log_file "$service")"
    {
        echo ""
        printf '%s\n' "===== $(date '+%Y-%m-%d %H:%M:%S') :: $(service_name "$service") start ====="
    } >> "$log_file"
}

wait_for_service_start() {
    local service="$1"
    local pid="$2"
    local attempt

    for attempt in $(seq 1 40); do
        if ! is_pid_running "$pid"; then
            return 1
        fi

        if [ -n "$(service_owned_port_pids "$service" | head -n 1 || true)" ]; then
            return 0
        fi

        sleep 0.25
    done

    return 0
}

start_service() {
    local service="$1"
    local pid_file log_file pid cmd dir url

    if adopt_service_if_running "$service"; then
        pid="$(tr -d '[:space:]' < "$(service_pid_file "$service")")"
        echo "[$(service_name "$service")] Already running (pid $pid) on $(service_url "$service")"
        return 0
    fi

    if [ -n "$(service_foreign_port_pids "$service" | head -n 1 || true)" ]; then
        print_service_conflict "$service"
        return 1
    fi

    pid_file="$(service_pid_file "$service")"
    log_file="$(service_log_file "$service")"
    dir="$(service_dir "$service")"
    url="$(service_url "$service")"

    write_log_header "$service"

    case "$service" in
        backend)
            cmd='exec poetry run python manage.py runserver 0.0.0.0:8000'
            ;;
        frontend)
            cmd='exec npm run dev'
            ;;
        *)
            echo "Unknown service: $service" >&2
            return 1
            ;;
    esac

    (
        cd "$dir"
        setsid bash -lc "$cmd" >> "$log_file" 2>&1 &
        printf '%s\n' "$!" > "$pid_file"
    )

    pid="$(tr -d '[:space:]' < "$pid_file")"
    if ! wait_for_service_start "$service" "$pid"; then
        echo "[$(service_name "$service")] Failed to start. Recent log output:"
        tail -n 40 "$log_file" || true
        rm -f "$pid_file"
        return 1
    fi

    echo "[$(service_name "$service")] Running on $url (pid $pid)"
    echo "[$(service_name "$service")] Log: $log_file"
}

collect_service_pids() {
    local service="$1"
    local pid

    cleanup_stale_pid_file "$service"

    if pid="$(service_managed_pid "$service" 2>/dev/null)"; then
        printf '%s\n' "$pid"
    fi

    service_owned_port_pids "$service"
}

kill_service_targets() {
    local signal="$1"
    local service="$2"
    local pid pgid
    declare -A seen_groups=()

    while read -r pid; do
        [ -n "$pid" ] || continue
        pgid="$(pid_pgid "$pid")"

        if [ -n "$pgid" ] && [ -z "${seen_groups[$pgid]+x}" ]; then
            seen_groups["$pgid"]=1
            kill "-$signal" "-$pgid" 2>/dev/null || kill "-$signal" "$pid" 2>/dev/null || true
        elif [ -z "$pgid" ]; then
            kill "-$signal" "$pid" 2>/dev/null || true
        fi
    done < <(collect_service_pids "$service" | awk 'NF && !seen[$0]++')
}

wait_for_service_stop() {
    local service="$1"
    local attempt

    for attempt in $(seq 1 40); do
        if [ -z "$(collect_service_pids "$service" | head -n 1 || true)" ]; then
            return 0
        fi
        sleep 0.25
    done

    return 1
}

stop_service() {
    local service="$1"
    local pid_file

    pid_file="$(service_pid_file "$service")"

    if [ -z "$(collect_service_pids "$service" | head -n 1 || true)" ]; then
        rm -f "$pid_file"
        echo "[$(service_name "$service")] Not running"
        return 0
    fi

    echo "[$(service_name "$service")] Stopping..."
    kill_service_targets TERM "$service"

    if ! wait_for_service_stop "$service"; then
        echo "[$(service_name "$service")] Still running after SIGTERM, forcing shutdown..."
        kill_service_targets KILL "$service"
        wait_for_service_stop "$service" || true
    fi

    rm -f "$pid_file"
    echo "[$(service_name "$service")] Stopped"
}

status_service() {
    local service="$1"
    local pid log_file

    log_file="$(service_log_file "$service")"

    if adopt_service_if_running "$service"; then
        pid="$(tr -d '[:space:]' < "$(service_pid_file "$service")")"
        echo "[$(service_name "$service")] running on $(service_url "$service") (pid $pid)"
        echo "[$(service_name "$service")] log: $log_file"
        return 0
    fi

    if [ -n "$(service_foreign_port_pids "$service" | head -n 1 || true)" ]; then
        print_service_conflict "$service"
        return 0
    fi

    echo "[$(service_name "$service")] stopped"
    echo "[$(service_name "$service")] log: $log_file"
}

show_logs() {
    local backend_tail frontend_tail

    ensure_state_dirs
    touch "$BACKEND_LOG_FILE" "$FRONTEND_LOG_FILE"

    echo "Following Libre Tiles dev logs. Ctrl+C detaches only."

    tail -n 40 -F "$BACKEND_LOG_FILE" 2>/dev/null | sed -u 's/^/[backend]  /' &
    backend_tail=$!
    tail -n 40 -F "$FRONTEND_LOG_FILE" 2>/dev/null | sed -u 's/^/[frontend] /' &
    frontend_tail=$!

    cleanup_logs() {
        kill "$backend_tail" "$frontend_tail" 2>/dev/null || true
        wait "$backend_tail" "$frontend_tail" 2>/dev/null || true
    }

    trap cleanup_logs EXIT INT TERM
    wait
}

start_all() {
    ensure_state_dirs

    if [ -z "$(service_owned_port_pids backend | head -n 1 || true)" ]; then
        if [ -n "$(service_foreign_port_pids backend | head -n 1 || true)" ]; then
            print_service_conflict backend
            return 1
        fi
    fi

    if [ -z "$(service_owned_port_pids frontend | head -n 1 || true)" ]; then
        if [ -n "$(service_foreign_port_pids frontend | head -n 1 || true)" ]; then
            print_service_conflict frontend
            return 1
        fi
    fi

    echo "============================================"
    echo "  Libre Tiles - Dev Supervisor"
    echo "============================================"
    echo ""

    if ! adopt_service_if_running backend; then
        prepare_backend
        start_service backend
    else
        start_service backend
    fi

    if ! adopt_service_if_running frontend; then
        prepare_frontend
        start_service frontend
    else
        start_service frontend
    fi

    echo ""
    echo "Open http://localhost:$FRONTEND_PORT to play."
    echo "Use ./scripts/libretiles.sh logs to follow output."
    echo "Use ./scripts/libretiles.sh stop to stop services."
}

stop_all() {
    ensure_state_dirs
    stop_service frontend
    stop_service backend
}

restart_all() {
    stop_all
    start_all
}

status_all() {
    ensure_state_dirs
    status_service backend
    status_service frontend
}

case "$COMMAND" in
    start)
        start_all
        ;;
    stop)
        stop_all
        ;;
    restart)
        restart_all
        ;;
    status)
        status_all
        ;;
    logs)
        show_logs
        ;;
    help|-h|--help)
        usage
        ;;
    *)
        echo "Unknown command: $COMMAND" >&2
        echo ""
        usage >&2
        exit 1
        ;;
esac
