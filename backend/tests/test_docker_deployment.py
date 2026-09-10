from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "docker-compose.yml"
NGINX = ROOT / "deploy/nginx/nginx.conf.template"
NGINX_ENTRYPOINT = ROOT / "deploy/nginx/entrypoint.sh"
NGINX_DOCKERFILE = ROOT / "deploy/nginx/Dockerfile"
CERTBOT_ENTRYPOINT = ROOT / "deploy/certbot/certbot.sh"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _service(text: str, name: str) -> str:
    match = re.search(
        rf"(?ms)^  {re.escape(name)}:\n(.*?)(?=^  [a-z][a-z0-9_-]*:\n|^networks:\n)",
        text,
    )
    assert match is not None, name
    return match.group(0)


def _cap_add(block: str) -> tuple[str, ...]:
    match = re.search(r"(?m)^    cap_add:\n((?:      - [A-Z0-9_]+\n?)+)", block)
    if match is None:
        return ()
    return tuple(re.findall(r"(?m)^      - ([A-Z0-9_]+)$", match.group(1)))


def _group_add(block: str) -> tuple[str, ...]:
    match = re.search(r"(?m)^    group_add:\n((?:      - \"[0-9]+\"\n?)+)", block)
    if match is None:
        return ()
    return tuple(re.findall(r'(?m)^      - "([0-9]+)"$', match.group(1)))


def _secret_sources(block: str) -> tuple[str, ...]:
    match = re.search(
        r"(?ms)^    secrets:\n(.*?)(?=^    [a-z][a-z0-9_-]*:|^  [a-z][a-z0-9_-]*:)",
        block,
    )
    if match is None:
        return ()
    return tuple(re.findall(r"(?m)^      - source: ([a-z][a-z0-9_]*)$", match.group(1)))


def _blocks(text: str, opening: str) -> list[str]:
    lines = text.splitlines()
    result: list[str] = []
    index = 0
    while index < len(lines):
        if not re.match(opening, lines[index]):
            index += 1
            continue
        start = index
        depth = lines[index].count("{") - lines[index].count("}")
        index += 1
        while index < len(lines) and depth:
            depth += lines[index].count("{") - lines[index].count("}")
            index += 1
        result.append("\n".join(lines[start:index]))
    return result


def _servers(text: str) -> list[str]:
    return _blocks(text, r"^    server\s*\{")


def _server_for_listener(text: str, listener: str) -> str:
    matches = [server for server in _servers(text) if f"listen {listener}" in server]
    assert len(matches) == 1, listener
    return matches[0]


def _locations(server: str) -> list[tuple[str, str]]:
    blocks = _blocks(server, r"^        location\s+.+\{\s*$")
    result = []
    for block in blocks:
        match = re.match(r"^\s*location\s+(.+?)\s*\{\s*$", block.splitlines()[0])
        assert match is not None
        result.append((match.group(1), block))
    return result


def _resolve(server: str, path: str) -> str:
    exact: list[tuple[str, str]] = []
    prefixes: list[tuple[str, str, bool]] = []
    regexes: list[tuple[str, str]] = []
    for matcher, block in _locations(server):
        if matcher.startswith("= "):
            exact.append((matcher[2:], block))
        elif matcher.startswith("~ "):
            regexes.append((matcher[2:], block))
        elif matcher.startswith("^~ "):
            prefixes.append((matcher[3:], block, True))
        else:
            prefixes.append((matcher, block, False))
    block = next((candidate for value, candidate in exact if value == path), "")
    if not block:
        candidates = [item for item in prefixes if path.startswith(item[0])]
        prefix = max(candidates, key=lambda item: len(item[0]), default=None)
        if prefix is not None and prefix[2]:
            block = prefix[1]
        else:
            block = next(
                (candidate for pattern, candidate in regexes if re.search(pattern, path)),
                prefix[1] if prefix is not None else "",
            )
    if "127.0.0.1:3000" in block:
        return "next"
    if "backend.sock" in block:
        return "django"
    if "return 404;" in block:
        return "deny"
    if "alias " in block:
        return "static"
    return "unmatched"


def test_production_compose_has_one_public_owner_and_no_default_password() -> None:
    compose = _text(COMPOSE)
    assert "POSTGRES_PASSWORD:" not in compose
    assert "POSTGRES_PASSWORD_FILE:" in compose
    for name in ("postgres", "redis", "backend-init", "backend", "nginx", "frontend", "certbot", "db-tools"):
        assert _service(compose, name)
    for name in ("postgres", "redis", "backend-init", "backend", "frontend", "certbot", "db-tools"):
        assert "\n    ports:" not in _service(compose, name)
    nginx = _service(compose, "nginx")
    assert "127.0.0.1:${ADMIN_PORT:-8443}:444" in nginx
    assert "${HTTP_BIND:-0.0.0.0}:${HTTP_PORT:-80}:80" in nginx
    assert "${HTTPS_BIND:-0.0.0.0}:${HTTPS_PORT:-443}:443" in nginx


def test_frontend_preserves_loopback_and_namespace_contract() -> None:
    compose = _text(COMPOSE)
    frontend = _service(compose, "frontend")
    nginx = _service(compose, "nginx")
    assert "network_mode: service:nginx" in frontend
    assert "HOSTNAME: 127.0.0.1" in frontend
    assert 'PORT: "3000"' in frontend
    assert "BACKEND_URL: http://127.0.0.1:8001" in frontend
    assert "\n    networks:" not in frontend
    assert "\n    ports:" not in frontend
    assert "\n    expose:" not in frontend
    assert "\n    hostname:" not in frontend
    assert re.search(r"depends_on:\n\s+nginx:\n\s+condition: service_healthy", frontend)
    assert "depends_on:" not in nginx
    assert "NET_BIND_SERVICE" in nginx
    assert 'net.ipv4.ip_unprivileged_port_start: "1024"' in nginx
    assert "- edge_egress_net" in nginx
    assert "data_net" not in nginx and "cache_net" not in nginx

    dockerfile = _text(ROOT / "frontend/Dockerfile")
    assert '["/usr/bin/env", "HOSTNAME=127.0.0.1", "PORT=3000", "node", "server.js"]' in dockerfile
    assert "USER 10003:10003" in dockerfile


def test_services_are_hardened_and_healthchecked() -> None:
    compose = _text(COMPOSE)
    for name in ("postgres", "redis", "backend-init", "backend", "frontend", "certbot", "db-tools"):
        block = _service(compose, name)
        assert "<<: *service-security" in block
        assert re.search(r'\n    user: "[1-9][0-9]*:[1-9][0-9]*"', block)
    for name in ("postgres", "redis", "backend", "frontend", "certbot"):
        assert "healthcheck:" in _service(compose, name)
    for name in ("nginx",):
        block = _service(compose, name)
        assert "<<: *service-security" in block
        assert "healthcheck:" in block
    assert "cap_add:" not in _service(compose, "frontend")
    assert "docker.sock" not in compose.lower()


def test_nginx_master_worker_split() -> None:
    compose = _text(COMPOSE)
    nginx = _service(compose, "nginx")
    assert re.search(r'\n    user: "0:10001"', nginx)
    assert "\n    init: false" in nginx
    assert _cap_add(nginx) == ("NET_BIND_SERVICE", "SETGID", "SETUID")
    for name in ("postgres", "redis", "backend-init", "backend", "frontend", "certbot", "db-tools"):
        assert _cap_add(_service(compose, name)) == (), name
    for capability in ("CHOWN", "DAC_OVERRIDE", "SYS_ADMIN"):
        assert capability not in nginx
    config = _text(NGINX)
    assert re.search(r"^user\s+edge\s+libretiles\s*;", config, re.M), (
        "nginx.conf.template must declare 'user edge libretiles;' for request workers"
    )
    dockerfile = _text(NGINX_DOCKERFILE)
    assert "USER 0:10001" in dockerfile, (
        "nginx Dockerfile must explicitly set USER 0:10001 for the master process"
    )


def test_nginx_runtime_tmpfs_ownership_is_explicit_and_not_shadowed() -> None:
    compose = _text(COMPOSE)
    nginx = _service(compose, "nginx")
    config = _text(NGINX)
    entrypoint = _text(NGINX_ENTRYPOINT)

    assert "- /tmp:" not in nginx
    assert "mode=1777" not in nginx
    assert "/run/nginx-master:size=4m,mode=0750,uid=0,gid=10001" in nginx
    temp_paths = {
        "client_body_temp_path": "/var/cache/nginx/client-body",
        "proxy_temp_path": "/var/cache/nginx/proxy",
        "fastcgi_temp_path": "/var/cache/nginx/fastcgi",
        "uwsgi_temp_path": "/var/cache/nginx/uwsgi",
        "scgi_temp_path": "/var/cache/nginx/scgi",
    }
    for directive, path in temp_paths.items():
        assert f"- {path}:size=8m,mode=0770,uid=10002,gid=10001" in nginx
        assert f"{directive} {path};" in config
    assert "pid /run/nginx-master/nginx.pid;" in config
    assert "config=/run/nginx-master/nginx.conf" in entrypoint
    assert "proxy_headers=/run/nginx-master/nginx-proxy-headers.conf" in entrypoint
    assert "callback_headers=/run/nginx-master/nginx-callback-headers.conf" in entrypoint
    assert "chown" not in entrypoint


def test_certificate_and_reload_state_remain_group_restricted() -> None:
    compose = _text(COMPOSE)
    nginx = _service(compose, "nginx")
    certbot = _service(compose, "certbot")
    script = _text(CERTBOT_ENTRYPOINT)
    validator = _text(ROOT / "scripts/validate_docker_deployment.sh")

    assert "backend_socket:/run/libretiles:ro" in nginx
    assert "certbot_config:/etc/letsencrypt:ro" in nginx
    assert "certbot_reload:/var/run/libretiles-certbot" in nginx
    assert 'user: "10002:10001"' in certbot
    assert "chmod 0750" in script
    assert 'chmod 0640 "$fullchain" "$privkey"' in script
    assert "touch \"$marker\"" in script
    assert not re.search(r"chmod\s+0?[67][67][67].*(?:privkey|letsencrypt|marker)", script)
    assert 'fullchain_link=$(readlink "$fullchain")' in validator
    assert 'privkey_link=$(readlink "$privkey")' in validator
    assert 'stat -c "%a %u %g %F" "$privkey"' in validator
    assert 'stat -Lc "%a %u %g %F" "$privkey"' in validator
    assert 'assert_metadata privkey_link_identity' in validator
    assert 'assert_metadata privkey_target "$privkey_target_meta" "640 10002 10001 regular file"' in validator
    assert 'assert_metadata "directory:$directory" "$directory_meta" "750 10002 10001 directory"' in validator
    assert "assert_metadata live_privkey_path" not in validator


def test_images_are_exact_version_and_manifest_digest_pinned() -> None:
    paths = (
        ROOT / "backend/Dockerfile",
        ROOT / "frontend/Dockerfile",
        ROOT / "deploy/nginx/Dockerfile",
        ROOT / "deploy/certbot/Dockerfile",
        ROOT / "deploy/postgres/Dockerfile",
    )
    from_line = re.compile(r"^FROM\s+\S+:[^\s@]+@sha256:[0-9a-f]{64}(?:\s+AS\s+\w+)?$", re.I)
    for path in paths:
        lines = [line for line in _text(path).splitlines() if line.startswith("FROM ")]
        assert lines and all(from_line.fullmatch(line) for line in lines), path
        assert all(":latest" not in line for line in lines)
    redis = _service(_text(COMPOSE), "redis")
    assert re.search(r"image: redis:\S+@sha256:[0-9a-f]{64}", redis)


def test_backend_virtualenv_keeps_its_build_and_runtime_path() -> None:
    dockerfile = _text(ROOT / "backend/Dockerfile")
    start = _text(ROOT / "backend/docker/start.sh")

    assert "python -m venv /app/.venv" in dockerfile
    assert "POETRY_VIRTUALENVS_CREATE=false" in dockerfile
    assert "VIRTUAL_ENV=/app/.venv" in dockerfile
    assert "POETRY_VIRTUALENVS_IN_PROJECT" not in dockerfile
    assert "COPY --from=builder --chown=10001:10001 /app/.venv /app/.venv" in dockerfile
    assert "PATH=/app/.venv/bin:$PATH" in dockerfile
    assert "poetry install --only main --no-root --no-interaction --no-ansi" in dockerfile
    assert "sed " not in dockerfile
    assert "exec daphne " in start
    assert "python -m daphne" not in start


def test_backend_socket_mode_contract_is_explicitly_enforced() -> None:
    start = _text(ROOT / "backend/docker/start.sh")
    validator = _text(ROOT / "scripts/validate_docker_deployment.sh")

    assert "umask 0007" in start
    assert '--endpoint "unix:${socket}:mode=0770"' in start
    assert "exec daphne " in start
    assert "python -m daphne" not in start
    assert "\ndaphne " not in start
    assert "&\n" not in start
    assert "trap " not in start

    assert "BACKEND_SOCKET_META" in validator
    assert "BACKEND_SOCKET_DIR_META" in validator
    assert "BACKEND_RUNTIME_IDENTITY" in validator
    assert "NGINX_RUNTIME_IDENTITY" in validator
    assert '"$socket_metadata" = "socket 770 10001:10001"' in validator
    assert "backend socket ownership/mode is wrong" in validator


def test_nginx_worker_process_probe_is_anchored() -> None:
    validator = _text(ROOT / "scripts/validate_docker_deployment.sh")

    assert "pgrep -f '^nginx: worker process'" in validator
    assert "pgrep -f 'nginx: worker'" not in validator


def test_paired_recreation_asserts_container_identity() -> None:
    validator = _text(ROOT / "scripts/validate_docker_deployment.sh")

    assert "RECREATE_IDS" in validator
    assert "RECREATE_NS" in validator
    assert '"$new_nginx_container_id" != "$old_nginx_container_id"' in validator
    assert '"$new_frontend_container_id" != "$old_frontend_container_id"' in validator
    assert '"$new_nginx_ns" = "$new_frontend_ns"' in validator
    assert '"$frontend_network_mode" = "container:$new_nginx_container_id"' in validator
    assert '"$new_nginx_ns" != "$old_ns"' not in validator


def test_asgi_initializes_django_before_importing_channels_routing() -> None:
    asgi = _text(ROOT / "backend/config/asgi.py")
    start = _text(ROOT / "backend/docker/start.sh")
    settings_default = 'os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")'
    django_initialization = "django_asgi_app = get_asgi_application()"
    deferred_imports = (
        "from channels.routing import ProtocolTypeRouter, URLRouter",
        "from channels.security.websocket import AllowedHostsOriginValidator",
        "from game.routing import websocket_urlpatterns",
    )

    assert asgi.splitlines()[:3] == ["import os", "", settings_default]
    for deferred_import in deferred_imports:
        assert asgi.index(settings_default) < asgi.index(deferred_import)
        assert asgi.index(django_initialization) < asgi.index(deferred_import)
    assert "DJANGO_SETTINGS_MODULE" not in start


def test_asgi_preserves_http_and_validated_websocket_router_shape() -> None:
    from channels.routing import ProtocolTypeRouter, URLRouter
    from channels.security.websocket import OriginValidator

    from config import asgi

    assert isinstance(asgi.application, ProtocolTypeRouter)
    assert set(asgi.application.application_mapping) == {"http", "websocket"}
    assert asgi.application.application_mapping["http"] is asgi.django_asgi_app
    websocket = asgi.application.application_mapping["websocket"]
    assert isinstance(websocket, OriginValidator)
    assert isinstance(websocket.application, URLRouter)
    assert websocket.application.routes is asgi.websocket_urlpatterns


def test_build_contexts_and_secret_mounts_exclude_secret_material() -> None:
    compose = _text(COMPOSE)
    for name in ("DJANGO_SECRET_KEY_FILE", "POSTGRES_PASSWORD_FILE", "FRONTEND_CREDENTIALS_FILE"):
        assert f"${{{name}:?" in compose
    for path in (ROOT / ".dockerignore", ROOT / "frontend/.dockerignore"):
        text = _text(path)
        assert ".env" in text
    dockerfiles = "\n".join(
        _text(path)
        for path in (
            ROOT / "backend/Dockerfile",
            ROOT / "frontend/Dockerfile",
            ROOT / "deploy/nginx/Dockerfile",
            ROOT / "deploy/certbot/Dockerfile",
            ROOT / "deploy/postgres/Dockerfile",
        )
    )
    assert not re.search(r"(?:COPY|ADD).*\.env", dockerfiles, re.I)
    assert not re.search(r"(?:ARG|ENV)\s+.*(?:PASSWORD|SECRET_KEY|API_KEY|TOKEN)", dockerfiles)


def test_production_secrets_use_only_the_dedicated_reader_group() -> None:
    compose = _text(COMPOSE)
    intended = {
        "postgres": ("postgres_password",),
        "backend-init": ("django_secret_key", "postgres_password"),
        "backend": ("django_secret_key", "postgres_password"),
        "frontend": ("frontend_credentials",),
        "db-tools": ("postgres_password",),
    }
    for service, expected_secrets in intended.items():
        block = _service(compose, service)
        assert _group_add(block) == ("10004",), service
        assert _secret_sources(block) == expected_secrets, service

    for service in ("nginx", "redis", "certbot"):
        block = _service(compose, service)
        assert _group_add(block) == (), service
        assert _secret_sources(block) == (), service

    assert not re.search(r"(?m)^        (?:uid|gid|mode):", compose)


def test_production_secret_source_policy_is_documented_and_validated() -> None:
    secret_docs = _text(ROOT / "deploy/secrets/README.md")
    vps_docs = _text(ROOT / "docs/vps_deployment_guide.md")
    env_example = _text(ROOT / ".env.docker.example")
    validator = _text(ROOT / "scripts/validate_docker_deployment.sh")

    for text in (secret_docs, vps_docs, env_example):
        assert "10004" in text
        assert "0440" in text
    assert "chown 0:10004" in secret_docs
    assert "atomic" in secret_docs.lower()
    assert "--network none" in validator
    assert "--cap-drop ALL" in validator
    assert "--cap-add CHOWN" in validator
    assert "SECRET_SOURCE_META" in validator
    assert "SECRET_TARGET_META" in validator
    assert "SECRET_READ_OK" in validator
    assert "SECRET_PATH_ABSENT" in validator


def test_validation_helper_search_window_is_bounded_and_restored() -> None:
    validator = _text(ROOT / "scripts/validate_docker_deployment.sh")
    compose = _text(COMPOSE)

    assert 'chmod 0701 "$TMP_ROOT/secrets"' in validator
    assert 'chmod 0700 "$TMP_ROOT/secrets"' in validator
    assert "restore_secret_directory_mode()" in validator
    assert "handle_secret_window_exit()" in validator
    assert "handle_secret_window_signal()" in validator
    assert "trap handle_secret_window_exit EXIT" in validator
    for signal in ("HUP", "INT", "TERM"):
        assert f"trap 'handle_secret_window_signal {signal}' {signal}" in validator
    assert "SECRET_WINDOW_META phase=before" in validator
    assert "SECRET_WINDOW_META phase=during" in validator
    assert "SECRET_WINDOW_FILE_META phase=during" in validator
    assert "SECRET_WINDOW_META phase=after" in validator

    helper_start = validator.index('docker run --name "$SECRET_HELPER"')
    helper_end = validator.index(
        '[ -z "$(docker ps -a --filter "name=^/${SECRET_HELPER}$"', helper_start
    )
    helper = validator[helper_start:helper_end]
    assert "--rm --network none --user 0:0 --read-only" in helper
    assert "--cap-drop ALL --cap-add CHOWN" in helper
    assert "--security-opt no-new-privileges:true" in helper
    assert "DAC_OVERRIDE" not in helper
    assert "CapPrm|CapEff|CapBnd|CapAmb|NoNewPrivs" in helper

    assert "0701" not in compose
    assert "DAC_OVERRIDE" not in compose
    assert not re.search(r"(?m)^        (?:uid|gid|mode):", compose)


def test_public_and_private_nginx_route_ownership() -> None:
    text = _text(NGINX)
    public = _server_for_listener(text, "443 ssl default_server;")
    cases = (
        ("/api/ai/move", "next"),
        ("/api/models", "next"),
        ("/api/prompts/", "next"),
        ("/api/admin/simulate/id/turn", "next"),
        ("/api/admin/users/", "django"),
        ("/api/catalog/models/", "django"),
        ("/api/game/id/", "django"),
        ("/api/auth/me/", "django"),
        ("/api/unknown/", "deny"),
        ("/static/admin/css/base.css", "deny"),
        ("/admin", "next"),
        ("/admin/replay/id", "next"),
        ("/", "next"),
    )
    for path, expected in cases:
        assert _resolve(public, path) == expected, path

    callback = _server_for_listener(text, "127.0.0.1:8001;")
    assert _resolve(callback, "/api/auth/me/") == "django"
    assert _resolve(callback, "/api/ai/move") == "deny"
    assert _resolve(callback, "/admin/") == "deny"

    private = _server_for_listener(text, "444 ssl;")
    assert _resolve(private, "/admin/") == "django"
    assert _resolve(private, "/static/admin/css/base.css") == "static"
    assert _resolve(private, "/api/game/id/") == "deny"


def test_nginx_proxy_headers_streaming_and_bootstrap_fail_closed() -> None:
    template = _text(NGINX)
    entrypoint = _text(NGINX_ENTRYPOINT)
    assert "$http_x_forwarded_proto" not in template
    assert "proxy_set_header X-Forwarded-For $remote_addr;" in template
    assert 'proxy_set_header Forwarded "";' in template
    assert "proxy_set_header Upgrade $http_upgrade;" in template
    assert "proxy_buffering off;" in template
    assert "proxy_request_buffering off;" in template
    assert "proxy_read_timeout 660s;" in template
    assert "proxy_read_timeout 3600s;" in template
    assert "__HTTP_FALLBACK__" in template
    assert "s/__HTTP_FALLBACK__/503/" in entrypoint
    assert "example.invalid" in entrypoint
    assert "nginx -t" in entrypoint
    assert "nginx -s reload" in entrypoint


def test_nginx_template_suppresses_nextjs_powered_by_header() -> None:
    template = _text(NGINX)
    assert "proxy_hide_header X-Powered-By;" in template, (
        "nginx template must suppress X-Powered-By to avoid "
        "leaking Next.js version on public responses"
    )


def test_full_mode_http_fallback_redirects_to_literal_validated_domain() -> None:
    entrypoint = _text(NGINX_ENTRYPOINT)
    template = _text(NGINX)
    validator = _text(ROOT / "scripts/validate_docker_deployment.sh")

    literal_fallback = "-e 's|__HTTP_FALLBACK__|301 https://'\"${DOMAIN}\"'$request_uri|'"
    assert literal_fallback in entrypoint, (
        "full-mode __HTTP_FALLBACK__ must embed the validated DOMAIN literally "
        "and keep $request_uri for the rendered nginx configuration"
    )
    assert "https://$host" not in entrypoint
    assert "s|__HTTP_FALLBACK__|301 https://$host$request_uri|" not in entrypoint

    assert "*[!A-Za-z0-9.-]*" in entrypoint, (
        "validate_domain must keep rejecting sed replacement metacharacters"
    )
    assert "s/__HTTP_FALLBACK__/503/" in entrypoint
    assert "server_name __DOMAIN__;" in template
    assert "if ($host != __DOMAIN__) {" in template
    assert "return 444;" in template

    assert "HTTP_FALLBACK_REDIRECT host=test.local" in validator
    assert "HTTP_FALLBACK_REDIRECT host=evil.local" in validator
    assert '"$canonical_port80" = "301 https://test.local/some/path?q=1"' in validator
    assert '"$noncanonical_port80" = "301 https://test.local/some/path?q=1"' in validator
    assert 'case "$noncanonical_port80" in *evil.local*)' in validator


def test_backup_restore_are_bounded_and_systemd_owner_is_removed() -> None:
    backup = _text(ROOT / "deploy/postgres/backup.sh")
    restore = _text(ROOT / "deploy/postgres/restore.sh")
    assert "--format=custom" in backup
    assert "--no-owner --no-acl" in backup
    assert "pg_restore --list" in backup
    assert "--confirm-disposable" in restore
    assert 'RESTORE_DISPOSABLE:-}" = "1"' in restore
    assert "restore target must differ" in restore
    for path in (
        ROOT / "backend/scripts/nginx/libretiles.conf",
        ROOT / "backend/scripts/systemd/libretiles-backend.service",
        ROOT / "backend/scripts/systemd/libretiles-frontend.service",
        ROOT / "backend/scripts/vps_preflight.sh",
        ROOT / "backend/scripts/vps_deploy.sh",
    ):
        assert not path.exists(), path
