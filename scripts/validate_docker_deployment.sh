#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
TMP_ROOT=/tmp/libretiles-docker-impl-01
PROJECT=libretiles-dvp-impl-01
ENV_FILE="$TMP_ROOT/.env.docker"
OVERRIDE_FILE="$TMP_ROOT/restore.compose.yml"
COMPOSE=(docker compose --project-directory "$ROOT_DIR" --env-file "$ENV_FILE" -p "$PROJECT" -f "$ROOT_DIR/docker-compose.yml")
IMAGE_PREFIX=libretiles-dvp-impl-01-
APP_VERSION=impl01
SECRET_HELPER=${PROJECT}-secret-owner-helper
IMAGES=(
    "${IMAGE_PREFIX}${APP_VERSION}-backend"
    "${IMAGE_PREFIX}${APP_VERSION}-frontend"
    "${IMAGE_PREFIX}${APP_VERSION}-nginx"
    "${IMAGE_PREFIX}${APP_VERSION}-certbot"
    "${IMAGE_PREFIX}${APP_VERSION}-postgres"
)

cleanup() {
    status=$?
    set +e
    docker rm -f "$SECRET_HELPER" >/dev/null 2>&1
    "${COMPOSE[@]}" --profile tls --profile ops -f "$OVERRIDE_FILE" down --volumes --remove-orphans >/dev/null 2>&1
    for image in "${IMAGES[@]}"; do
        docker image rm "$image" >/dev/null 2>&1 || true
    done
    rm -rf -- "$TMP_ROOT"
    exit "$status"
}
trap cleanup EXIT HUP INT TERM

fail() {
    printf 'FAIL: %s\n' "$1" >&2
    exit 1
}

restore_secret_directory_mode() {
    chmod 0700 "$TMP_ROOT/secrets"
}

handle_secret_window_exit() {
    status=$?
    trap - EXIT HUP INT TERM
    if ! restore_secret_directory_mode; then
        printf '%s\n' 'FAIL: could not restore synthetic secret directory to mode 0700' >&2
        exit 1
    fi
    exit "$status"
}

handle_secret_window_signal() {
    signal=$1
    trap - EXIT HUP INT TERM
    if ! restore_secret_directory_mode; then
        printf '%s\n' 'FAIL: could not restore synthetic secret directory after signal' >&2
        exit 1
    fi
    case "$signal" in
        HUP) exit 129 ;;
        INT) exit 130 ;;
        TERM) exit 143 ;;
        *) exit 1 ;;
    esac
}

assert_no_synthetic_value() {
    path=$1
    context=$2
    if grep -Eq 'SYNTHETIC-django-key|synthetic-postgres-password' "$path"; then
        fail "$context exposed a synthetic secret"
    fi
}

compose_up() {
    label=$1
    shift
    output="$TMP_ROOT/compose-up-$label.log"
    set +e
    "$@" >"$output" 2>&1
    status=$?
    set -e
    assert_no_synthetic_value "$output" "Compose $label output"
    if [ "$status" -ne 0 ]; then
        failure_logs="$TMP_ROOT/compose-up-$label-services.log"
        : >"$failure_logs"
        docker ps -a --filter "label=com.docker.compose.project=$PROJECT" --format '{{.Names}}' |
            while IFS= read -r container; do
                [ -z "$container" ] || {
                    printf 'CONTAINER_LOG name=%s\n' "$container"
                    docker logs --tail 200 "$container" 2>&1 || true
                }
            done >>"$failure_logs"
        assert_no_synthetic_value "$failure_logs" "Compose $label service logs"
        cat "$output" >&2
        cat "$failure_logs" >&2
        fail "Compose $label startup exited $status"
    fi
    cat "$output"
}

assert_secret_source() {
    name=$1
    path=$2
    metadata=$(stat -c '%F %u:%g %a' "$path")
    printf 'SECRET_SOURCE_META name=%s value=%s\n' "$name" "$metadata"
    [ "$metadata" = "regular file 0:10004 440" ] || fail "$name source metadata is not 0:10004/0440"
}

assert_reader_container() {
    container=$1
    shift
    groups=$(docker exec "$container" id -G)
    printf '%s\n' "$groups" | tr ' ' '\n' | grep -qx 10004 || fail "$container lacks secret-reader GID 10004"
    for secret in "$@"; do
        path="/run/secrets/$secret"
        case "$secret" in
            django_secret_key) source="$TMP_ROOT/secrets/django" ;;
            postgres_password) source="$TMP_ROOT/secrets/postgres" ;;
            frontend_credentials) source="$TMP_ROOT/secrets/frontend.json" ;;
            *) fail "unknown secret role $secret" ;;
        esac
        mount=$(docker inspect --format "{{range .Mounts}}{{if eq .Destination \"$path\"}}{{.Type}}|{{.Source}}|{{.RW}}{{end}}{{end}}" "$container")
        printf 'SECRET_MOUNT service=%s name=%s value=%s\n' "$container" "$secret" "$mount"
        [ "$mount" = "bind|$source|false" ] || fail "$container $secret is not the expected read-only bind mount"
        metadata=$(docker exec "$container" stat -c '%F %u:%g %a' "$path")
        printf 'SECRET_TARGET_META service=%s name=%s value=%s\n' "$container" "$secret" "$metadata"
        [ "$metadata" = "regular file 0:10004 440" ] || fail "$container $secret target metadata is not 0:10004/0440"
        docker exec "$container" sh -c 'dd if="$1" of=/dev/null bs=1 count=1 status=none' sh "$path" \
            >/dev/null 2>&1 || fail "$container cannot read $secret as its service identity"
        printf 'SECRET_READ_OK service=%s name=%s\n' "$container" "$secret"
    done
}

assert_secret_absent() {
    container=$1
    secret=$2
    docker exec "$container" test ! -e "/run/secrets/$secret" || fail "$container can see unrelated $secret"
    printf 'SECRET_PATH_ABSENT service=%s name=%s\n' "$container" "$secret"
}

assert_no_secret_group() {
    container=$1
    groups=$(docker exec "$container" id -G)
    if printf '%s\n' "$groups" | tr ' ' '\n' | grep -qx 10004; then
        fail "$container unexpectedly has secret-reader GID 10004"
    fi
    printf 'SECRET_GROUP_ABSENT service=%s gid=10004\n' "$container"
}

wait_health() {
    service=$1
    container="${PROJECT}-${service}-1"
    for _ in $(seq 1 90); do
        state=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container" 2>/dev/null || true)
        case "$state" in
            healthy) return 0 ;;
            unhealthy|exited|dead) docker logs "$container" >&2 || true; fail "$service became $state" ;;
        esac
        sleep 2
    done
    docker logs "$container" >&2 || true
    fail "$service did not become healthy"
}

[ ! -e "$TMP_ROOT" ] || fail "$TMP_ROOT already exists"
install -d -m 0700 "$TMP_ROOT" "$TMP_ROOT/secrets" "$TMP_ROOT/cert-source"
printf '%s\n' 'SYNTHETIC-django-key-for-disposable-validation-only-0123456789abcdef' >"$TMP_ROOT/secrets/django"
printf '%s\n' 'synthetic-postgres-password-for-disposable-validation' >"$TMP_ROOT/secrets/postgres"
printf '%s\n' '{}' >"$TMP_ROOT/secrets/frontend.json"
chmod 0600 "$TMP_ROOT/secrets/django" "$TMP_ROOT/secrets/postgres" "$TMP_ROOT/secrets/frontend.json"

cat >"$ENV_FILE" <<EOF
DOMAIN=test.local
ACME_EMAIL=admin@test.local
APP_VERSION=$APP_VERSION
IMAGE_PREFIX=$IMAGE_PREFIX
POSTGRES_DB=libretiles_test
POSTGRES_USER=libretiles_test
POSTGRES_DATA_VOLUME=${PROJECT}-postgres-data
POSTGRES_BACKUP_VOLUME=${PROJECT}-postgres-backups
CERTBOT_CONFIG_VOLUME=${PROJECT}-certbot-config
HTTP_BIND=127.0.0.1
HTTP_PORT=18080
HTTPS_BIND=127.0.0.1
HTTPS_PORT=18443
ADMIN_PORT=18444
DJANGO_SECRET_KEY_FILE=$TMP_ROOT/secrets/django
POSTGRES_PASSWORD_FILE=$TMP_ROOT/secrets/postgres
FRONTEND_CREDENTIALS_FILE=$TMP_ROOT/secrets/frontend.json
EOF
chmod 0600 "$ENV_FILE"

cat >"$OVERRIDE_FILE" <<EOF
services:
  restore-postgres:
    image: ${IMAGE_PREFIX}${APP_VERSION}-postgres
    user: "70:70"
    read_only: true
    cap_drop: ["ALL"]
    security_opt: ["no-new-privileges:true"]
    environment:
      POSTGRES_DB: libretiles_restore
      POSTGRES_USER: libretiles_test
      POSTGRES_PASSWORD_FILE: /run/secrets/postgres_password
    secrets:
      - source: postgres_password
        target: postgres_password
    group_add:
      - "10004"
    volumes:
      - restore_data:/var/lib/postgresql/data
    tmpfs:
      - /tmp:size=32m,mode=1770,uid=70,gid=70
      - /var/run/postgresql:size=8m,mode=0770,uid=70,gid=70
    networks: ["data_net"]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -q -U libretiles_test -d libretiles_restore"]
      interval: 2s
      timeout: 2s
      retries: 30
volumes:
  restore_data: {}
EOF

"${COMPOSE[@]}" --profile tls --profile ops config >"$TMP_ROOT/rendered-compose.yml"
assert_no_synthetic_value "$TMP_ROOT/rendered-compose.yml" "Compose configuration"

cp "$ENV_FILE" "$TMP_ROOT/missing-secret.env"
printf '%s\n' "POSTGRES_PASSWORD_FILE=$TMP_ROOT/secrets/absent" >>"$TMP_ROOT/missing-secret.env"

"${COMPOSE[@]}" --profile tls --profile ops build
for image in "${IMAGES[@]}"; do
    user=$(docker image inspect --format '{{.Config.User}}' "$image")
    if echo "$image" | grep -q nginx; then
        # nginx master runs as root (UID 0); request workers drop to edge identity
        [ "$user" = "0:10001" ] || fail "$image must have root/shared-group (0:10001) master user"
    else
        [ -n "$user" ] && [ "${user%%:*}" != "0" ] || fail "$image has a root runtime user"
    fi
    if docker history --no-trunc "$image" | grep -Eq 'SYNTHETIC-django-key|synthetic-postgres-password'; then
        fail "$image history contains a synthetic secret"
    fi
done

(
    trap handle_secret_window_exit EXIT
    trap 'handle_secret_window_signal HUP' HUP
    trap 'handle_secret_window_signal INT' INT
    trap 'handle_secret_window_signal TERM' TERM

    private_identity="$(id -u):$(id -g)"
    root_metadata=$(stat -c '%F %u:%g %a' "$TMP_ROOT")
    directory_metadata=$(stat -c '%F %u:%g %a' "$TMP_ROOT/secrets")
    printf 'SECRET_WINDOW_META phase=before path=root value=%s\n' "$root_metadata"
    printf 'SECRET_WINDOW_META phase=before path=secrets value=%s\n' "$directory_metadata"
    [ "$root_metadata" = "directory $private_identity 700" ] || fail "synthetic root is not private before helper window"
    [ "$directory_metadata" = "directory $private_identity 700" ] || fail "synthetic secret directory is not private before helper window"
    for secret in django postgres frontend.json; do
        file_metadata=$(stat -c '%F %u:%g %a' "$TMP_ROOT/secrets/$secret")
        printf 'SECRET_WINDOW_FILE_META phase=before name=%s value=%s\n' "$secret" "$file_metadata"
        [ "$file_metadata" = "regular file $private_identity 600" ] || fail "$secret is not private before helper window"
    done

    chmod 0701 "$TMP_ROOT/secrets"
    root_metadata=$(stat -c '%F %u:%g %a' "$TMP_ROOT")
    directory_metadata=$(stat -c '%F %u:%g %a' "$TMP_ROOT/secrets")
    printf 'SECRET_WINDOW_META phase=during path=root value=%s\n' "$root_metadata"
    printf 'SECRET_WINDOW_META phase=during path=secrets value=%s\n' "$directory_metadata"
    [ "$root_metadata" = "directory $private_identity 700" ] || fail "synthetic root changed during helper window"
    [ "$directory_metadata" = "directory $private_identity 701" ] || fail "synthetic secret search window is not mode 0701"
    for secret in django postgres frontend.json; do
        file_metadata=$(stat -c '%F %u:%g %a' "$TMP_ROOT/secrets/$secret")
        printf 'SECRET_WINDOW_FILE_META phase=during name=%s value=%s\n' "$secret" "$file_metadata"
        [ "$file_metadata" = "regular file $private_identity 600" ] || fail "$secret became readable during helper window"
    done

    docker run --name "$SECRET_HELPER" --rm --network none --user 0:0 --read-only \
        --cap-drop ALL --cap-add CHOWN --security-opt no-new-privileges:true \
        --mount "type=bind,src=$TMP_ROOT/secrets,dst=/secrets" \
        --entrypoint sh "${IMAGE_PREFIX}${APP_VERSION}-postgres" -ec '
            printf "%s\n" SECRET_HELPER_PROCESS_STATUS
            awk "/^(Uid|Gid|Groups|CapPrm|CapEff|CapBnd|CapAmb|NoNewPrivs):/" /proc/self/status
            directory_metadata=$(stat -c "%F %u:%g %a" /secrets)
            printf "SECRET_HELPER_DIRECTORY_META value=%s\n" "$directory_metadata"
            [ "$directory_metadata" = "directory 1000:1000 701" ]
            chown 0:10004 /secrets/django /secrets/postgres /secrets/frontend.json
            printf "%s\n" "SECRET_HELPER_CHOWN_STATUS=0"
            chmod 0440 /secrets/django /secrets/postgres /secrets/frontend.json
            printf "%s\n" "SECRET_HELPER_CHMOD_STATUS=0"
            for secret in django postgres frontend.json; do
                metadata=$(stat -c "%F %u:%g %a" "/secrets/$secret")
                printf "SECRET_HELPER_FILE_META name=%s value=%s\n" "$secret" "$metadata"
                [ "$metadata" = "regular file 0:10004 440" ]
            done
        '
)
[ -z "$(docker ps -a --filter "name=^/${SECRET_HELPER}$" --format '{{.Names}}')" ] || fail "secret ownership helper did not exit cleanly"
restored_metadata=$(stat -c '%F %u:%g %a' "$TMP_ROOT/secrets")
printf 'SECRET_WINDOW_META phase=after path=secrets value=%s\n' "$restored_metadata"
[ "$restored_metadata" = "directory $(id -u):$(id -g) 700" ] || fail "synthetic secret directory is not private"
assert_secret_source django_secret_key "$TMP_ROOT/secrets/django"
assert_secret_source postgres_password "$TMP_ROOT/secrets/postgres"
assert_secret_source frontend_credentials "$TMP_ROOT/secrets/frontend.json"

if docker compose --project-directory "$ROOT_DIR" --env-file "$TMP_ROOT/missing-secret.env" -p "$PROJECT" -f "$ROOT_DIR/docker-compose.yml" up -d postgres >/dev/null 2>&1; then
    fail "Compose started a service with a missing secret file"
fi

compose_up bootstrap "${COMPOSE[@]}" up -d nginx
wait_health nginx
[ "$(curl -sS -o /dev/null -w '%{http_code}' http://127.0.0.1:18080/healthz)" = "200" ] || fail "bootstrap health failed"
[ "$(curl -sS -o /dev/null -w '%{http_code}' -H 'Host: test.local' http://127.0.0.1:18080/)" = "503" ] || fail "bootstrap exposed plaintext application traffic"

openssl req -x509 -newkey rsa:2048 -nodes -days 2 -subj /CN=test.local \
    -keyout "$TMP_ROOT/cert-source/privkey1.pem" \
    -out "$TMP_ROOT/cert-source/fullchain1.pem" >/dev/null 2>&1
chmod 0600 "$TMP_ROOT/cert-source/privkey1.pem" "$TMP_ROOT/cert-source/fullchain1.pem"
tar -C "$TMP_ROOT/cert-source" -cf - fullchain1.pem privkey1.pem | \
    "${COMPOSE[@]}" --profile tls run -T --rm --no-deps --entrypoint sh certbot -c \
    'set -eu; umask 0027; mkdir -p /etc/letsencrypt/archive/test.local /etc/letsencrypt/live/test.local; tar -xf - -C /etc/letsencrypt/archive/test.local; ln -s ../../archive/test.local/fullchain1.pem /etc/letsencrypt/live/test.local/fullchain.pem; ln -s ../../archive/test.local/privkey1.pem /etc/letsencrypt/live/test.local/privkey.pem; chmod 0700 /etc/letsencrypt/live /etc/letsencrypt/archive /etc/letsencrypt/live/test.local /etc/letsencrypt/archive/test.local; chmod 0600 /etc/letsencrypt/archive/test.local/fullchain1.pem /etc/letsencrypt/archive/test.local/privkey1.pem; /usr/local/bin/certbot.sh signal-reload'

for _ in $(seq 1 30); do
    code=$(curl -k -sS -o /dev/null -w '%{http_code}' --resolve test.local:18443:127.0.0.1 https://test.local:18443/ || true)
    [ "$code" = "502" ] && break
    sleep 1
done
[ "${code:-}" = "502" ] || fail "TLS edge did not enter full mode with bounded pre-frontend 502"
"${COMPOSE[@]}" --profile tls run -T --rm --no-deps --entrypoint sh certbot -c \
    'set -eu
    assert_metadata() {
        predicate=$1
        actual=$2
        expected=$3
        [ "$actual" = "$expected" ] || {
            printf "CERT_PREDICATE_FAIL name=%s actual=%s expected=%s\n" "$predicate" "$actual" "$expected" >&2
            exit 1
        }
    }
    fullchain=/etc/letsencrypt/live/test.local/fullchain.pem
    privkey=/etc/letsencrypt/live/test.local/privkey.pem
    fullchain_link=$(readlink "$fullchain")
    privkey_link=$(readlink "$privkey")
    fullchain_link_meta=$(stat -c "%a %u %g %F" "$fullchain")
    privkey_link_meta=$(stat -c "%a %u %g %F" "$privkey")
    fullchain_target_meta=$(stat -Lc "%a %u %g %F" "$fullchain")
    privkey_target_meta=$(stat -Lc "%a %u %g %F" "$privkey")
    printf "CERT_LINK name=fullchain value=%s\n" "$fullchain_link"
    printf "CERT_LINK name=privkey value=%s\n" "$privkey_link"
    printf "CERT_LINK_META name=fullchain value=%s\n" "$fullchain_link_meta"
    printf "CERT_LINK_META name=privkey value=%s\n" "$privkey_link_meta"
    printf "CERT_TARGET_META name=fullchain value=%s\n" "$fullchain_target_meta"
    printf "CERT_TARGET_META name=privkey value=%s\n" "$privkey_target_meta"
    for directory in /etc/letsencrypt /etc/letsencrypt/live /etc/letsencrypt/archive \
        /etc/letsencrypt/live/test.local /etc/letsencrypt/archive/test.local; do
        directory_meta=$(stat -c "%a %u %g %F" "$directory")
        printf "CERT_DIR_META path=%s value=%s\n" "$directory" "$directory_meta"
        assert_metadata "directory:$directory" "$directory_meta" "750 10002 10001 directory"
    done
    assert_metadata fullchain_link "$fullchain_link" "../../archive/test.local/fullchain1.pem"
    assert_metadata privkey_link "$privkey_link" "../../archive/test.local/privkey1.pem"
    assert_metadata fullchain_link_identity "$(stat -c "%u %g %F" "$fullchain")" "10002 10001 symbolic link"
    assert_metadata privkey_link_identity "$(stat -c "%u %g %F" "$privkey")" "10002 10001 symbolic link"
    assert_metadata fullchain_target "$fullchain_target_meta" "640 10002 10001 regular file"
    assert_metadata privkey_target "$privkey_target_meta" "640 10002 10001 regular file"'
docker exec "${PROJECT}-nginx-1" test ! -e /var/run/libretiles-certbot/reload-request || fail "nginx could not consume the issue-style reload marker through group access"

openssl req -x509 -newkey rsa:2048 -nodes -days 2 -subj /CN=test.local \
    -keyout "$TMP_ROOT/cert-source/privkey2.pem" \
    -out "$TMP_ROOT/cert-source/fullchain2.pem" >/dev/null 2>&1
chmod 0600 "$TMP_ROOT/cert-source/privkey2.pem" "$TMP_ROOT/cert-source/fullchain2.pem"
tar -C "$TMP_ROOT/cert-source" -cf - fullchain2.pem privkey2.pem | \
    "${COMPOSE[@]}" --profile tls run -T --rm --no-deps --entrypoint sh certbot -c \
    'set -eu; umask 0027; tar -xf - -C /etc/letsencrypt/archive/test.local; chmod 0600 /etc/letsencrypt/archive/test.local/fullchain2.pem /etc/letsencrypt/archive/test.local/privkey2.pem; ln -sfn ../../archive/test.local/fullchain2.pem /etc/letsencrypt/live/test.local/fullchain.pem; ln -sfn ../../archive/test.local/privkey2.pem /etc/letsencrypt/live/test.local/privkey.pem; chmod 0700 /etc/letsencrypt/live/test.local /etc/letsencrypt/archive/test.local; /usr/local/bin/certbot.sh signal-reload'
for _ in $(seq 1 30); do
    docker exec "${PROJECT}-nginx-1" test ! -e /var/run/libretiles-certbot/reload-request && break
    sleep 1
done
docker exec "${PROJECT}-nginx-1" test ! -e /var/run/libretiles-certbot/reload-request || fail "nginx could not consume the renewal-style reload marker through group access"

compose_up full "${COMPOSE[@]}" up -d postgres redis backend-init backend frontend
wait_health postgres
wait_health redis
wait_health backend
wait_health frontend

canonical_port80=$(curl -sS -o /dev/null -w '%{http_code} %{redirect_url}' -H 'Host: test.local' 'http://127.0.0.1:18080/some/path?q=1')
printf 'HTTP_FALLBACK_REDIRECT host=test.local value=%s\n' "$canonical_port80"
[ "$canonical_port80" = "301 https://test.local/some/path?q=1" ] || fail "canonical port-80 full-mode redirect is wrong (got $canonical_port80)"
noncanonical_port80=$(curl -sS -o /dev/null -w '%{http_code} %{redirect_url}' -H 'Host: evil.local' 'http://127.0.0.1:18080/some/path?q=1')
printf 'HTTP_FALLBACK_REDIRECT host=evil.local value=%s\n' "$noncanonical_port80"
[ "$noncanonical_port80" = "301 https://test.local/some/path?q=1" ] || fail "non-canonical port-80 full-mode redirect is wrong (got $noncanonical_port80)"
case "$noncanonical_port80" in *evil.local*) fail "port-80 full-mode redirect reflected the request Host";; esac

assert_reader_container "${PROJECT}-postgres-1" postgres_password
assert_secret_absent "${PROJECT}-postgres-1" django_secret_key
assert_secret_absent "${PROJECT}-postgres-1" frontend_credentials

assert_reader_container "${PROJECT}-backend-1" django_secret_key postgres_password
assert_secret_absent "${PROJECT}-backend-1" frontend_credentials

assert_reader_container "${PROJECT}-frontend-1" frontend_credentials
assert_secret_absent "${PROJECT}-frontend-1" django_secret_key
assert_secret_absent "${PROJECT}-frontend-1" postgres_password

"${COMPOSE[@]}" run -T --rm --no-deps --entrypoint sh backend-init -ec '
    id -G | tr " " "\n" | grep -qx 10004
    for secret in django_secret_key postgres_password; do
        metadata=$(stat -c "%F %u:%g %a" "/run/secrets/$secret")
        [ "$metadata" = "regular file 0:10004 440" ]
        printf "SECRET_TARGET_META service=backend-init name=%s value=%s\n" "$secret" "$metadata"
        dd if="/run/secrets/$secret" of=/dev/null bs=1 count=1 status=none
        printf "SECRET_READ_OK service=backend-init name=%s\n" "$secret"
    done
    test ! -e /run/secrets/frontend_credentials
    printf "SECRET_PATH_ABSENT service=backend-init name=frontend_credentials\n"
'

"${COMPOSE[@]}" --profile ops run -T --rm --no-deps --entrypoint sh db-tools -ec '
    id -G | tr " " "\n" | grep -qx 10004
    metadata=$(stat -c "%F %u:%g %a" /run/secrets/postgres_password)
    [ "$metadata" = "regular file 0:10004 440" ]
    printf "SECRET_TARGET_META service=db-tools name=postgres_password value=%s\n" "$metadata"
    dd if=/run/secrets/postgres_password of=/dev/null bs=1 count=1 status=none
    printf "SECRET_READ_OK service=db-tools name=postgres_password\n"
    test ! -e /run/secrets/django_secret_key
    test ! -e /run/secrets/frontend_credentials
    printf "SECRET_PATH_ABSENT service=db-tools name=django_secret_key\n"
    printf "SECRET_PATH_ABSENT service=db-tools name=frontend_credentials\n"
'

assert_no_secret_group "${PROJECT}-nginx-1"
assert_secret_absent "${PROJECT}-nginx-1" django_secret_key
assert_secret_absent "${PROJECT}-nginx-1" postgres_password
assert_secret_absent "${PROJECT}-nginx-1" frontend_credentials
assert_no_secret_group "${PROJECT}-redis-1"
assert_secret_absent "${PROJECT}-redis-1" django_secret_key
assert_secret_absent "${PROJECT}-redis-1" postgres_password
assert_secret_absent "${PROJECT}-redis-1" frontend_credentials
"${COMPOSE[@]}" --profile tls run -T --rm --no-deps --entrypoint sh certbot -ec '
    ! id -G | tr " " "\n" | grep -qx 10004
    test ! -e /run/secrets/django_secret_key
    test ! -e /run/secrets/postgres_password
    test ! -e /run/secrets/frontend_credentials
    printf "SECRET_GROUP_ABSENT service=certbot gid=10004\n"
    printf "SECRET_PATH_ABSENT service=certbot name=django_secret_key\n"
    printf "SECRET_PATH_ABSENT service=certbot name=postgres_password\n"
    printf "SECRET_PATH_ABSENT service=certbot name=frontend_credentials\n"
'

curl_tls=(curl -k -sS --resolve test.local:18443:127.0.0.1)
[ "$("${curl_tls[@]}" -o /dev/null -w '%{http_code}' https://test.local:18443/)" = "200" ] || fail "frontend route failed"
[ "$("${curl_tls[@]}" -o /dev/null -w '%{http_code}' https://test.local:18443/api/catalog/models/)" = "200" ] || fail "Django catalog route failed"
[ "$("${curl_tls[@]}" -o /dev/null -w '%{http_code}' https://test.local:18443/api/unknown/)" = "404" ] || fail "unknown API did not fail closed"
[ "$("${curl_tls[@]}" -o /dev/null -w '%{http_code}' https://test.local:18443/static/admin/css/base.css)" = "404" ] || fail "public Django static was exposed"
admin_code=$(curl -k -sS -o /dev/null -w '%{http_code}' --resolve test.local:18444:127.0.0.1 https://test.local:18444/admin/)
case "$admin_code" in 200|302) ;; *) fail "private Django admin route failed" ;; esac
forged_code=$("${curl_tls[@]}" -o /dev/null -w '%{http_code}' -H 'X-Forwarded-Proto: http' -H 'X-Forwarded-For: 203.0.113.9' https://test.local:18443/api/catalog/models/)
[ "$forged_code" = "200" ] || fail "forwarding-header overwrite failed"

nginx_ns=$(docker exec "${PROJECT}-nginx-1" readlink /proc/1/ns/net)
frontend_ns=$(docker exec "${PROJECT}-frontend-1" readlink /proc/1/ns/net)
backend_ns=$(docker exec "${PROJECT}-backend-1" readlink /proc/1/ns/net)
[ "$nginx_ns" = "$frontend_ns" ] || fail "frontend and nginx do not share a network namespace"
[ "$nginx_ns" != "$backend_ns" ] || fail "backend unexpectedly shares the edge namespace"
[ "$(docker inspect --format '{{.HostConfig.NetworkMode}}' "${PROJECT}-frontend-1")" = "container:$(docker inspect --format '{{.Id}}' "${PROJECT}-nginx-1")" ] || fail "frontend network_mode does not resolve to nginx"
docker exec "${PROJECT}-frontend-1" test ! -e /run/libretiles/backend.sock || fail "frontend can see the backend socket"

backend_runtime_identity=$(docker exec "${PROJECT}-backend-1" sh -c 'printf "uid=%s gid=%s groups=%s" "$(id -u)" "$(id -g)" "$(id -G | tr " " ",")"')
printf 'BACKEND_RUNTIME_IDENTITY value=%s\n' "$backend_runtime_identity"
nginx_runtime_identity=$(docker exec "${PROJECT}-nginx-1" sh -c 'printf "uid=%s gid=%s groups=%s" "$(id -u)" "$(id -g)" "$(id -G | tr " " ",")"')
printf 'NGINX_RUNTIME_IDENTITY value=%s\n' "$nginx_runtime_identity"
socket_metadata=$(docker exec "${PROJECT}-backend-1" stat -c '%F %a %u:%g' /run/libretiles/backend.sock)
socket_directory_metadata=$(docker exec "${PROJECT}-backend-1" stat -c '%F %a %u:%g' /run/libretiles)
printf 'BACKEND_SOCKET_META path=/run/libretiles/backend.sock value=%s\n' "$socket_metadata"
printf 'BACKEND_SOCKET_DIR_META path=/run/libretiles value=%s\n' "$socket_directory_metadata"
[ "$socket_metadata" = "socket 770 10001:10001" ] || fail "backend socket ownership/mode is wrong (got $socket_metadata)"

frontend_caps=$(docker exec "${PROJECT}-frontend-1" sh -c "awk '/CapEff/ {print \$2}' /proc/1/status")
[ "$frontend_caps" = "0000000000000000" ] || fail "frontend retained capabilities"

nginx_master_name=$(docker exec "${PROJECT}-nginx-1" cat /proc/1/comm)
[ "$nginx_master_name" = "nginx" ] || fail "nginx master is not PID 1 (got $nginx_master_name)"
nginx_master_uid=$(docker exec "${PROJECT}-nginx-1" awk '/^Uid:/ {print $2}' /proc/1/status)
nginx_master_gid=$(docker exec "${PROJECT}-nginx-1" awk '/^Gid:/ {print $2}' /proc/1/status)
nginx_master_groups=$(docker exec "${PROJECT}-nginx-1" awk '/^Groups:/ {print $2}' /proc/1/status)
[ "$nginx_master_uid" = "0" ] || fail "nginx master PID 1 is not UID 0"
[ "$nginx_master_gid" = "10001" ] || fail "nginx master PID 1 is not GID 10001"
[ "$nginx_master_groups" = "10001" ] || fail "nginx master has unexpected supplementary groups ($nginx_master_groups)"
for cap_field in CapPrm CapEff CapBnd; do
    nginx_master_caps=$(docker exec "${PROJECT}-nginx-1" awk -v field="$cap_field:" '$1 == field {print $2}' /proc/1/status)
    [ "$nginx_master_caps" = "00000000000004c0" ] || fail "nginx master $cap_field differs from exact NET_BIND_SERVICE,SETGID,SETUID set (got $nginx_master_caps)"
done
nginx_master_ambient=$(docker exec "${PROJECT}-nginx-1" awk '/CapAmb/ {print $2}' /proc/1/status)
[ "$nginx_master_ambient" = "0000000000000000" ] || fail "nginx master has ambient capabilities"

nginx_worker_pids=$(docker exec "${PROJECT}-nginx-1" sh -c "pgrep -f '^nginx: worker process' 2>/dev/null || true")
if [ -n "$nginx_worker_pids" ]; then
    for wpid in $nginx_worker_pids; do
        worker_uid=$(docker exec "${PROJECT}-nginx-1" awk '/^Uid:/ {print $2}' "/proc/$wpid/status" 2>/dev/null || true)
        worker_gid=$(docker exec "${PROJECT}-nginx-1" awk '/^Gid:/ {print $2}' "/proc/$wpid/status" 2>/dev/null || true)
        worker_caps=$(docker exec "${PROJECT}-nginx-1" awk '/CapEff/ {print $2}' "/proc/$wpid/status" 2>/dev/null || true)
        [ "$worker_uid" = "10002" ] || fail "nginx worker PID $wpid has UID $worker_uid, expected 10002"
        [ "$worker_gid" = "10001" ] || fail "nginx worker PID $wpid has GID $worker_gid, expected 10001"
        [ "$worker_caps" = "0000000000000000" ] || fail "nginx worker PID $wpid has effective capabilities"
    done
else
    fail "no nginx worker processes found"
fi

docker exec --user 10002:10001 "${PROJECT}-nginx-1" sh -c '
    set -eu
    [ "$(awk "/CapEff/ {print \$2}" /proc/self/status)" = "0000000000000000" ]
    for directory in /var/cache/nginx/client-body /var/cache/nginx/proxy \
        /var/cache/nginx/fastcgi /var/cache/nginx/uwsgi /var/cache/nginx/scgi; do
        [ "$(stat -c "%a %u %g" "$directory")" = "770 10002 10001" ]
        probe="$directory/.worker-write-probe"
        : >"$probe"
        rm "$probe"
    done
' || fail "worker identity could not write every dedicated nginx temp tmpfs"

for svc in postgres redis backend frontend; do
    svc_uid=$(docker exec "${PROJECT}-${svc}-1" id -u 2>/dev/null || true)
    [ "$svc_uid" != "0" ] || fail "$svc runs as root"
    svc_caps=$(docker exec "${PROJECT}-${svc}-1" sh -c "awk '/CapEff/ {print \$2}' /proc/1/status" 2>/dev/null || true)
    [ "$svc_caps" = "0000000000000000" ] || fail "$svc has effective capabilities ($svc_caps)"
done
if docker exec "${PROJECT}-frontend-1" node -e 'require("node:net").createServer().listen(445,"127.0.0.1").on("listening",()=>process.exit(0)).on("error",()=>process.exit(1))'; then
    fail "frontend could bind a protected low port"
fi

postgres_ip=$(docker inspect --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "${PROJECT}-postgres-1")
if docker exec "${PROJECT}-frontend-1" node -e 'const s=require("node:net").connect({host:process.argv[1],port:5432,timeout:1000});s.on("connect",()=>process.exit(0));s.on("error",()=>process.exit(1));s.on("timeout",()=>process.exit(1))' "$postgres_ip"; then
    fail "frontend reached the PostgreSQL network"
fi

old_ns=$nginx_ns
old_nginx_container_id=$(docker inspect --format '{{.Id}}' "${PROJECT}-nginx-1")
old_frontend_container_id=$(docker inspect --format '{{.Id}}' "${PROJECT}-frontend-1")
compose_up recreate "${COMPOSE[@]}" up -d --force-recreate nginx frontend
wait_health nginx
wait_health frontend
new_nginx_container_id=$(docker inspect --format '{{.Id}}' "${PROJECT}-nginx-1")
new_frontend_container_id=$(docker inspect --format '{{.Id}}' "${PROJECT}-frontend-1")
new_nginx_ns=$(docker exec "${PROJECT}-nginx-1" readlink /proc/1/ns/net)
new_frontend_ns=$(docker exec "${PROJECT}-frontend-1" readlink /proc/1/ns/net)
frontend_network_mode=$(docker inspect --format '{{.HostConfig.NetworkMode}}' "${PROJECT}-frontend-1")
printf 'RECREATE_IDS old_nginx=%s new_nginx=%s old_frontend=%s new_frontend=%s\n' \
    "$old_nginx_container_id" "$new_nginx_container_id" "$old_frontend_container_id" "$new_frontend_container_id"
printf 'RECREATE_NS old_nginx_ns=%s new_nginx_ns=%s new_frontend_ns=%s\n' "$old_ns" "$new_nginx_ns" "$new_frontend_ns"
[ "$new_nginx_container_id" != "$old_nginx_container_id" ] || fail "paired recreation did not replace the nginx container"
[ "$new_frontend_container_id" != "$old_frontend_container_id" ] || fail "paired recreation did not replace the frontend container"
[ "$new_nginx_ns" = "$new_frontend_ns" ] || fail "paired recreation broke the shared network namespace"
[ "$frontend_network_mode" = "container:$new_nginx_container_id" ] || fail "recreated frontend does not join the recreated nginx network namespace"
docker exec "${PROJECT}-nginx-1" nginx -s reload -c /run/nginx-master/nginx.conf
wait_health frontend

"${COMPOSE[@]}" --profile ops run --rm db-tools backup smoke.dump
"${COMPOSE[@]}" --profile ops run --rm db-tools verify smoke.dump
compose_up restore "${COMPOSE[@]}" -f "$OVERRIDE_FILE" up -d restore-postgres
wait_health restore-postgres
"${COMPOSE[@]}" --profile ops run --rm --no-deps \
    --entrypoint /usr/local/bin/restore.sh \
    -e RESTORE_DISPOSABLE=1 -e RESTORE_DB_HOST=restore-postgres \
    -e RESTORE_DB_NAME=libretiles_restore -e RESTORE_DB_USER=libretiles_test \
    db-tools restore --confirm-disposable smoke.dump
source_count=$(docker exec "${PROJECT}-postgres-1" psql -U libretiles_test -d libretiles_test -Atqc "select count(*) from django_migrations")
restore_count=$(docker exec "${PROJECT}-restore-postgres-1" psql -U libretiles_test -d libretiles_restore -Atqc "select count(*) from django_migrations")
[ "$source_count" = "$restore_count" ] || fail "restore rehearsal migration count differs"

for service in postgres redis backend nginx frontend; do
    [ "$(docker inspect --format '{{.HostConfig.ReadonlyRootfs}}' "${PROJECT}-${service}-1")" = "true" ] || fail "$service root filesystem is writable"
done

docker inspect "${PROJECT}-postgres-1" "${PROJECT}-redis-1" "${PROJECT}-backend-1" "${PROJECT}-nginx-1" "${PROJECT}-frontend-1" >"$TMP_ROOT/container-inspect.json"
"$ROOT_DIR/backend/.venv/bin/python" - "$TMP_ROOT/container-inspect.json" <<'PY'
import json
import sys

containers = json.load(open(sys.argv[1], encoding="utf-8"))
published = {}
for container in containers:
    name = container["Name"].lstrip("/")
    bindings = container["HostConfig"].get("PortBindings") or {}
    if bindings:
        published[name] = bindings
assert list(published) == ["libretiles-dvp-impl-01-nginx-1"], published
assert set(published.values().__iter__().__next__()) == {"80/tcp", "443/tcp", "444/tcp"}
PY

"${COMPOSE[@]}" logs --no-color --tail 200 >"$TMP_ROOT/compose.log"
if grep -Eq 'SYNTHETIC-django-key|synthetic-postgres-password' "$TMP_ROOT/compose.log"; then
    fail "container logs exposed synthetic secrets"
fi

printf '%s\n' 'Docker deployment validation passed.'
