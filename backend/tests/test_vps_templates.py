from __future__ import annotations

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
NGINX = BACKEND / "scripts/nginx/libretiles.conf"
PREFLIGHT = BACKEND / "scripts/vps_preflight.sh"
DEPLOY = BACKEND / "scripts/vps_deploy.sh"
BACKEND_UNIT = BACKEND / "scripts/systemd/libretiles-backend.service"
FRONTEND_UNIT = BACKEND / "scripts/systemd/libretiles-frontend.service"


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
    return _blocks(text, r"^server\s*\{")


def _locations(server: str) -> list[tuple[str, str]]:
    blocks = _blocks(server, r"^\s*location\s+.+\{\s*$")
    locations = []
    for block in blocks:
        match = re.match(r"^\s*location\s+(.+?)\s*\{\s*$", block.splitlines()[0])
        assert match is not None
        locations.append((match.group(1), block))
    return locations


def _server_for_port(text: str, port: int) -> str:
    matches = [
        server
        for server in _servers(text)
        if re.search(rf"^\s*listen\s+[^;]*\b{port}(?:\s|;)", server, re.MULTILINE)
    ]
    assert len(matches) == 1
    return matches[0]


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
        prefix_matches = [item for item in prefixes if path.startswith(item[0])]
        prefix_match = max(prefix_matches, key=lambda item: len(item[0]), default=None)
        if prefix_match is not None and prefix_match[2]:
            block = prefix_match[1]
        else:
            block = next(
                (candidate for pattern, candidate in regexes if re.search(pattern, path)),
                prefix_match[1] if prefix_match is not None else "",
            )

    if "proxy_pass http://127.0.0.1:3000;" in block:
        return "next"
    if "proxy_pass http://127.0.0.1:8000;" in block:
        return "daphne"
    if "return 404;" in block:
        return "deny"
    if "alias " in block:
        return "static"
    return "unmatched"


def _proxy_headers(block: str) -> dict[str, str]:
    return dict(re.findall(r"^\s*proxy_set_header\s+(\S+)\s+(.+);$", block, re.MULTILINE))


def test_public_nginx_route_ownership() -> None:
    text = NGINX.read_text()
    public = _server_for_port(text, 443)
    cases = (
        ("/api/ai/move", "next"),
        ("/api/ai/judge", "next"),
        ("/api/models", "next"),
        ("/api/models/", "next"),
        ("/api/prompts", "next"),
        ("/api/prompts/", "next"),
        ("/api/admin/simulate/abc/turn", "next"),
        ("/api/admin/simulate/abc/turn/", "next"),
        ("/api/admin/users/", "daphne"),
        ("/api/catalog/models/", "daphne"),
        ("/api/game/example/", "daphne"),
        ("/api/auth/me/", "daphne"),
        ("/api", "deny"),
        ("/api/unknown/", "deny"),
        ("/admin", "next"),
        ("/admin/replay/example", "next"),
        ("/static/admin/css/base.css", "deny"),
        ("/settings", "next"),
    )
    for path, expected in cases:
        assert _resolve(public, path) == expected, path

    assert "location ^~ /api/admin/" not in public
    assert "proxy_pass http://127.0.0.1:8000/" not in public


def test_nginx_private_listeners_and_callback_routes() -> None:
    text = NGINX.read_text()
    callback = _server_for_port(text, 8001)
    admin = _server_for_port(text, 8443)
    assert re.search(r"^\s*listen\s+127\.0\.0\.1:8001;", callback, re.MULTILINE)
    assert re.search(r"^\s*listen\s+127\.0\.0\.1:8443\s+ssl;", admin, re.MULTILINE)

    callback_cases = (
        ("/api/auth/me/", "daphne"),
        ("/api/catalog/models/", "daphne"),
        ("/api/game/example/", "daphne"),
        ("/api/admin/simulate/example/start/", "daphne"),
        ("/api/ai/move", "deny"),
        ("/admin/", "deny"),
        ("/", "deny"),
    )
    for path, expected in callback_cases:
        assert _resolve(callback, path) == expected, path

    for _, block in _locations(callback):
        if "proxy_pass " not in block:
            continue
        headers = _proxy_headers(block)
        assert headers["Host"] == "YOUR_DOMAIN"
        assert headers["X-Forwarded-Host"] == "YOUR_DOMAIN"
        assert headers["X-Forwarded-Proto"] == "https"
        assert headers["X-Forwarded-Port"] == "443"

    assert _resolve(admin, "/admin/") == "daphne"
    assert _resolve(admin, "/static/admin/css/base.css") == "static"
    assert _resolve(admin, "/api/game/example/") == "deny"


def test_every_nginx_proxy_has_complete_stripping_headers() -> None:
    text = NGINX.read_text()
    assert "$http_x_forwarded_proto" not in text
    required = {
        "Host",
        "X-Forwarded-Host",
        "X-Forwarded-Proto",
        "X-Forwarded-Port",
        "X-Forwarded-For",
        "X-Real-IP",
        "Forwarded",
    }
    for server in _servers(text):
        listens = " ".join(re.findall(r"^\s*listen\s+(.+);$", server, re.MULTILINE))
        for matcher, block in _locations(server):
            if "proxy_pass " not in block:
                continue
            headers = _proxy_headers(block)
            assert required <= headers.keys(), matcher
            assert headers["X-Forwarded-For"] == "$remote_addr"
            assert headers["Forwarded"] == '""'
            assert "proxy_cache off;" in block
            if "127.0.0.1:8001" in listens:
                assert headers["X-Forwarded-Proto"] == "https"
            else:
                assert headers["X-Forwarded-Proto"] == "$scheme"


def test_nginx_websocket_and_sse_contracts() -> None:
    text = NGINX.read_text()
    public = _server_for_port(text, 443)
    locations = dict(_locations(public))
    websocket = locations["/ws/"]
    assert "proxy_http_version 1.1;" in websocket
    assert "proxy_set_header Upgrade $http_upgrade;" in websocket
    assert "proxy_set_header Connection $libretiles_connection_upgrade;" in websocket
    assert "proxy_read_timeout 3600s;" in websocket
    assert "map $http_upgrade $libretiles_connection_upgrade" in text

    for matcher in ("^~ /api/ai/", "~ ^/api/admin/simulate/[^/]+/turn/?$"):
        stream = locations[matcher]
        for directive in (
            "proxy_buffering off;",
            "proxy_request_buffering off;",
            "gzip off;",
            "proxy_read_timeout 660s;",
            "proxy_send_timeout 660s;",
        ):
            assert directive in stream


def test_nginx_has_no_preload_policy() -> None:
    text = NGINX.read_text().lower()
    assert "preload" not in text
    assert "strict-transport-security" not in text


def test_systemd_units_are_non_root_and_loopback_only() -> None:
    backend = BACKEND_UNIT.read_text()
    frontend = FRONTEND_UNIT.read_text()
    for unit in (backend, frontend):
        assert "User=libretiles" in unit
        assert "Group=libretiles" in unit
        assert "EnvironmentFile=-" not in unit
        assert "NoNewPrivileges=true" in unit
        assert "PrivateTmp=true" in unit
        assert "ProtectSystem=full" in unit
        assert "ProtectHome=true" in unit
        assert "ExecStartPre=" not in unit
    assert "EnvironmentFile=PROJECT_ROOT/backend/.env" in backend
    assert "EnvironmentFile=PROJECT_ROOT/frontend/.env.local" in frontend
    assert ".venv/bin/daphne -b 127.0.0.1 -p 8000" in backend
    assert "config.asgi:application" in backend
    assert "--proxy-headers" not in backend
    assert "gunicorn" not in backend.lower()
    assert "next start --hostname 127.0.0.1 --port 3000" in frontend


def test_deployment_script_guards_and_boundaries() -> None:
    preflight = PREFLIGHT.read_text()
    deploy = DEPLOY.read_text()
    for script in (preflight, deploy):
        assert script.startswith("#!/bin/bash\nset -euo pipefail\n")
        assert "ufw enable" not in script.lower()
        assert "certbot" not in script.lower()
    assert "--confirm-vps" in deploy
    assert "exit 2" in deploy
    assert deploy.index('case "${1:-}" in') < deploy.index("id -u")
    assert "--install-site" in deploy
    assert "poetry install --only main --no-root" in deploy
    assert "npm ci --include=dev" in deploy
    assert deploy.index("npm ci --include=dev") < deploy.index("npm run build")
    assert deploy.index("manage.py check") < deploy.index("manage.py migrate --noinput")
    assert deploy.index("manage.py migrate --noinput") < deploy.index("manage.py seed_models")
    assert deploy.index("manage.py seed_models") < deploy.index("manage.py collectstatic --noinput")
    assert "git " not in deploy
    assert "poetry update" not in deploy
    assert "sync_openrouter_models" not in deploy
    assert "DJANGO_SECURE_PROXY_SSL_HEADER=" not in deploy
    assert "sites-available/libretiles.conf" in deploy
    assert "status != 0 && site_pending" in deploy
    assert deploy.index("systemctl restart \"$FRONTEND_UNIT\"") < deploy.index(
        "systemctl reload nginx"
    )


def test_preflight_requires_pinned_runtime_ranges_and_read_only_ufw() -> None:
    preflight = PREFLIGHT.read_text()
    assert "python3.12 -m venv --help" in preflight
    assert "node_major == 20 && node_minor >= 19" in preflight
    assert "node_major == 22 && node_minor >= 12" in preflight
    assert "node_major >= 24" in preflight
    assert "poetry_major == 2" in preflight
    assert "poetry_minor == 3 && poetry_patch >= 2" in preflight
    assert "systemctl is-active --quiet" in preflight
    assert "ufw status" in preflight
    assert "sudo" not in preflight


def test_templates_contain_only_placeholders_for_host_identity() -> None:
    nginx = NGINX.read_text()
    assert "YOUR_DOMAIN" in nginx
    assert "PROJECT_ROOT" in nginx
    assert "CERTIFICATE_PATH" in nginx
    assert "CERTIFICATE_KEY_PATH" in nginx
    assert not re.search(r"server_name\s+(?!YOUR_DOMAIN)[^;]+;", nginx)


def test_scripts_parse_as_bash_without_execution() -> None:
    for script in (PREFLIGHT, DEPLOY):
        result = subprocess.run(
            ["/bin/bash", "-n", str(script)],
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr


def test_next_standalone_output_remains_deferred() -> None:
    next_config = (ROOT / "frontend/next.config.ts").read_text()
    assert not re.search(r"\boutput\s*:\s*['\"]standalone['\"]", next_config)
