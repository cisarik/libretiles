"""Mechanical guard: the repository must not teach wildcard Django binds or Vercel hosting.

Whole 16 landed a production VPS architecture with strict loopback binds and a self-hosted
standalone Next.js server. This module makes it impossible to silently reintroduce the old
instructions through documentation edits.

Offline and cheap: standard library only, no Django import, explicit path list (never walk
the tree), zero subprocess, no dotenv reads. Target under 0.5 seconds.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]

_SCAN: tuple[Path, ...] = (
    _REPO / "README.md",
    _REPO / "AGENTS.md",
    _REPO / "CONTRIBUTING.md",
    _REPO / "libretiles_PRD.md",
    _REPO / "docs" / "architecture.md",
    _REPO / "docs" / "vps_deployment_guide.md",
    _REPO / "frontend" / "README.md",
    _REPO / "scripts" / "start-backend.sh",
    _REPO / "scripts" / "libretiles.sh",
    _REPO / "backend" / "config" / "settings.py",
    _REPO / "backend" / ".env.example",
)

def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# --- Bind assertions ----------------------------------------------------------

def test_no_documented_django_wildcard_bind() -> None:
    """No documentation or dev script may instruct binding Django to 0.0.0.0:8000."""
    forbidden = re.compile(r"(?<![\d.])0\.0\.0\.0\s*:\s*8000\b")
    for path in _SCAN:
        for match in forbidden.finditer(_text(path)):
            raise AssertionError(
                f"{path.relative_to(_REPO)} contains Django wildcard bind "
                f"{match.group()!r}; use 127.0.0.1:8000"
            )


def test_documented_backend_commands_use_loopback() -> None:
    """README, AGENTS, and CONTRIBUTING must teach explicit loopback Django launch commands."""
    loopback = re.compile(r"\bmanage\.py\s+runserver\s+127\.0\.0\.1:8000\b")
    expectations = {
        "README.md": 2,
        "AGENTS.md": 1,
        "CONTRIBUTING.md": 1,
    }
    for name, expected in expectations.items():
        path = _REPO / name
        actual = len(loopback.findall(_text(path)))
        assert actual == expected, (
            f"{name} must contain {expected} explicit Django loopback command(s); "
            f"found {actual}"
        )


def test_backend_launch_scripts_use_loopback() -> None:
    """Both backend launch scripts must exec Django on 127.0.0.1:8000."""
    start_sh = (_REPO / "scripts" / "start-backend.sh").read_text(encoding="utf-8")
    assert "poetry run python manage.py runserver 127.0.0.1:8000" in start_sh, (
        "scripts/start-backend.sh is missing executable loopback launch "
        "'poetry run python manage.py runserver 127.0.0.1:8000'; preserve the Poetry wrapper"
    )
    ltsh = (_REPO / "scripts" / "libretiles.sh").read_text(encoding="utf-8")
    expected = "cmd='exec poetry run python manage.py runserver 127.0.0.1:8000'"
    assert expected in ltsh, (
        f"scripts/libretiles.sh is missing executable loopback launch {expected!r}; "
        "preserve the Poetry wrapper"
    )


# --- Deployment assertions ------------------------------------------------

def _strip_md(text: str) -> str:
    """Remove Markdown backtick/emphasis so patterns match **Vercel** and `Vercel`."""
    return re.sub(r"[*_`]+", "", text)


def test_no_vercel_deployment_venue_claims() -> None:
    """No documentation may claim the frontend is deployed on or hosted by Vercel."""
    venue_patterns = [
        re.compile(r"\b(?:deploy(?:ed|ment)?|host(?:ed|ing)?)\s+(?:(?:on|to)\s+)?vercel\b", re.IGNORECASE),
        re.compile(r"\bfrontend\s*:\s*vercel\b", re.IGNORECASE),
        re.compile(r"\ballow\s+vercel\s+frontend\b", re.IGNORECASE),
        re.compile(r"\bvercel\s*\+\s*vps\b", re.IGNORECASE),
    ]
    for path in _SCAN:
        normalized = _strip_md(" ".join(_text(path).split()))
        for pat in venue_patterns:
            m = pat.search(normalized)
            if m:
                raise AssertionError(
                    f"{path.relative_to(_REPO)} contains stale Vercel venue claim "
                    f"{m.group()!r}; describe the self-hosted VPS deployment"
                )


def test_authoritative_deployment_descriptions_are_present() -> None:
    """Key documents must describe the self-hosted VPS standalone deployment."""
    agents = _text(_REPO / "AGENTS.md")
    assert "self-hosted VPS" in agents, "AGENTS.md missing 'self-hosted VPS'"
    assert "standalone" in agents, "AGENTS.md missing 'standalone'"
    assert "127.0.0.1:3000" in agents, "AGENTS.md missing loopback bind '127.0.0.1:3000'"
    assert "nginx" in agents, "AGENTS.md missing 'nginx'"

    prd = _text(_REPO / "libretiles_PRD.md")
    assert "standalone server" in prd, "libretiles_PRD.md missing 'standalone server'"
    assert "self-hosted VPS" in prd, "libretiles_PRD.md missing 'self-hosted VPS'"
    assert "nginx" in prd, "libretiles_PRD.md missing 'nginx'"

    arch = _text(_REPO / "docs" / "architecture.md")
    assert "self-hosted VPS" in arch, "docs/architecture.md missing 'self-hosted VPS'"

    vps = _text(_REPO / "docs" / "vps_deployment_guide.md")
    assert "HOSTNAME=127.0.0.1" in vps, "vps_deployment_guide.md missing 'HOSTNAME=127.0.0.1'"
    assert "127.0.0.1:8000" in vps, "vps_deployment_guide.md missing '127.0.0.1:8000'"

    settings = _text(_REPO / "backend" / "config" / "settings.py")
    assert "# CORS — frontend origins allowed to call this API" in settings, (
        "settings.py missing corrected CORS comment"
    )


def test_prd_phase_seven_names_standalone_vps_deployment() -> None:
    """PRD Phase 7 must describe Next.js standalone + Daphne/Django on self-hosted VPS."""
    prd = _text(_REPO / "libretiles_PRD.md")
    expected = (
        "7. **Phase 7**: Deployment (self-hosted VPS: Next.js standalone + "
        "Daphne/Django behind nginx). Stripe is rejected for this product direction."
    )
    assert expected in prd, (
        "libretiles_PRD.md Phase 7 must describe Next.js standalone and "
        "Daphne/Django behind nginx on a self-hosted VPS"
    )


def test_vercel_ai_sdk_library_references_are_preserved() -> None:
    """Vercel AI SDK library references must survive venue-claim removal."""
    prd = _text(_REPO / "libretiles_PRD.md")
    sdk_hits = prd.count("Vercel AI SDK")
    assert sdk_hits >= 2, (
        f"libretiles_PRD.md lost its Vercel AI SDK library references; "
        f"found {sdk_hits}, expected at least 2"
    )
    arch = _text(_REPO / "docs" / "architecture.md")
    assert "Vercel AI SDK" in arch, (
        "docs/architecture.md lost its Vercel AI SDK library reference"
    )


# --- Debug-prose assertions ------------------------------------------------

def test_throttle_prose_names_django_debug() -> None:
    """README and .env.example must use DJANGO_DEBUG, not bare DEBUG=true."""
    readme = _text(_REPO / "README.md")
    expected = 'Unused for local `DJANGO_DEBUG=true` boot.'
    assert expected in readme, (
        f"README.md throttle row must contain {expected!r}"
    )
    bare_debug = re.compile(r"(?<![\w])DEBUG\s*=\s*['\"]?true\b")
    assert not bare_debug.search(readme), (
        "README.md uses bare DEBUG=true; name the environment variable DJANGO_DEBUG=true"
    )

    env_example = _text(_REPO / "backend" / ".env.example")
    assert expected in env_example, (
        f"backend/.env.example must contain {expected!r}"
    )
    assert "DJANGO_DEBUG='true'" in env_example, (
        "backend/.env.example missing DJANGO_DEBUG='true' assignment"
    )
    assert not bare_debug.search(env_example), (
        "backend/.env.example uses bare DEBUG=true; name the environment variable DJANGO_DEBUG=true"
    )
