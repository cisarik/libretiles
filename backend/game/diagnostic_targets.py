"""Diagnostic-only OpenAI-compatible target policy (S7).

One URL policy shared with the TypeScript runtime (plan D2): HTTPS, implicit
or ``:443`` only, exact canonical-ASCII hostname equality with an active
allowed-host row, and refusals for userinfo, IP literals, Unicode/``xn--``
hosts, trailing dots, queries, fragments, ``.``/``..`` path segments, and
percent-escapes. ``model_id`` is metadata and never a URL.

Save-time DNS uses ``getaddrinfo(AF_UNSPEC, SOCK_STREAM)`` bounded to ~2s,
requires at least one result, refuses the whole name when ANY resolved
address falls outside the public-unicast policy, never connects, and never
persists resolved addresses as authority.

FAKE MODE ONLY: this module performs no sockets beyond the bounded
``getaddrinfo`` call; tests inject ``resolve_host_addresses``.
"""

from __future__ import annotations

import concurrent.futures
import ipaddress
import re
import socket
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, cast

CREDENTIAL_ENV_NAMES = (
    "GROQ_API_KEY",
    "GEMINI_API_KEY",
    "MISTRAL_API_KEY",
    "AION_API_KEY",
    "HF_TOKEN",
    "CLOUDFLARE_ACCOUNT_ID",
    "CLOUDFLARE_API_TOKEN",
    "OPENROUTER_API_KEY",
    "NVIDIA_API_KEY",
    "IBM_CLOUD_API_KEY",
    "IBM_WATSONX_PROJECT_ID",
    "IBM_WATSONX_REGION",
)

CHAT_COMPLETIONS_SUFFIX = "/chat/completions"
DNS_TIMEOUT_SECONDS = 2.0
MAX_HOSTNAME_LENGTH = 253

_LABEL_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_IPV4_CANDIDATE_PATTERN = re.compile(r"^[0-9.]+$")
_ASCII_NETLOC_PATTERN = re.compile(r"^[\x21-\x7e]+$")

_REFUSED_IPV4_NETWORKS = tuple(
    ipaddress.ip_network(network)
    for network in (
        "0.0.0.0/8",
        "10.0.0.0/8",
        "100.64.0.0/10",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "172.16.0.0/12",
        "192.0.0.0/24",
        "192.0.2.0/24",
        "192.88.99.0/24",
        "192.168.0.0/16",
        "198.18.0.0/15",
        "198.51.100.0/24",
        "203.0.113.0/24",
        "224.0.0.0/4",
        "240.0.0.0/4",
        "168.63.129.16/32",
    )
)
_GLOBAL_UNICAST_V6_MIN = cast(
    ipaddress.IPv6Address, ipaddress.ip_address("2000::")
)
_GLOBAL_UNICAST_V6_MAX = cast(
    ipaddress.IPv6Address, ipaddress.ip_address("3fff:ffff:ffff:ffff:ffff:ffff:ffff:ffff")
)
_REFUSED_IPV6_NETWORKS = tuple(
    ipaddress.ip_network(network)
    for network in (
        "2001::/23",
        "2001:db8::/32",
        "2002::/16",
        "3fff::/20",
        "::/128",
        "::1/128",
        "fe80::/10",
        "fc00::/7",
        "ff00::/8",
        "::ffff:0:0/96",
        "64:ff9b::/96",
    )
)


class DiagnosticTargetError(Exception):
    """Fail-closed diagnostic-target policy violation.

    ``code`` is a stable short identifier (``hostname_invalid``,
    ``dns_refused``, ``frozen``, ``credential_env_unknown``, ...); the
    message carries no secret value and never a resolved address.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class TargetURL:
    """Parsed, policy-checked diagnostic target base URL."""

    raw: str
    hostname: str
    path: str
    canonical_base: str

    @property
    def canonical_chat_completions(self) -> str:
        return self.canonical_base + CHAT_COMPLETIONS_SUFFIX


def canonical_hostname(host: str) -> str:
    """Validate and return a canonical ASCII hostname. Exact-match only.

    The input must already be canonical lowercase: mixed case, trailing dots,
    percent escapes, IP literals, punycode, and single labels are refused
    rather than silently normalized.
    """
    stripped = (host or "").strip()
    if not stripped:
        raise DiagnosticTargetError("hostname_invalid", "hostname is empty")
    lowered = stripped.lower()
    if lowered != stripped:
        raise DiagnosticTargetError(
            "hostname_not_canonical", "hostname must already be canonical lowercase"
        )
    if len(lowered) > MAX_HOSTNAME_LENGTH:
        raise DiagnosticTargetError("hostname_invalid", "hostname exceeds 253 characters")
    if not _ASCII_NETLOC_PATTERN.fullmatch(lowered):
        raise DiagnosticTargetError("hostname_invalid", "hostname carries non-ASCII characters")
    if "%" in lowered:
        raise DiagnosticTargetError("hostname_invalid", "hostname carries a percent-escape")
    if lowered.endswith("."):
        raise DiagnosticTargetError("hostname_trailing_dot", "hostname ends with a dot")
    if ":" in lowered:
        raise DiagnosticTargetError("hostname_invalid", "hostname is an IPv6 literal")
    if _IPV4_CANDIDATE_PATTERN.fullmatch(lowered):
        raise DiagnosticTargetError("hostname_ip_literal", "hostname is an IPv4 literal")
    labels = lowered.split(".")
    if len(labels) < 2:
        raise DiagnosticTargetError("hostname_single_label", "hostname needs at least two labels")
    for label in labels:
        if not label:
            raise DiagnosticTargetError("hostname_empty_label", "hostname carries an empty label")
        if label.startswith("xn--"):
            raise DiagnosticTargetError("hostname_punycode", "punycode labels are refused")
        if not _LABEL_PATTERN.fullmatch(label):
            raise DiagnosticTargetError(
                "hostname_invalid", "hostname label is not canonical LDH"
            )
    return lowered


def _refuse(code: str, message: str) -> None:
    raise DiagnosticTargetError(code, message)


def parse_target_base_url(base_url: str) -> TargetURL:
    """The ONE URL policy. Raises DiagnosticTargetError on any violation."""
    raw = base_url or ""
    if not raw.strip():
        _refuse("url_empty", "base_url is empty")
    from urllib.parse import urlsplit

    parts = urlsplit(raw)
    if parts.scheme != "https":
        _refuse("scheme_not_https", "base_url must use HTTPS")
    netloc = parts.netloc
    if not netloc:
        _refuse("url_no_host", "base_url carries no host")
    if "@" in netloc:
        _refuse("url_userinfo", "base_url carries userinfo")
    if "%" in netloc:
        _refuse("url_percent_escape_host", "base_url host carries a percent-escape")
    if not _ASCII_NETLOC_PATTERN.fullmatch(netloc):
        _refuse("url_non_ascii_host", "base_url host carries non-ASCII characters")
    if ":" in netloc:
        port = netloc.rsplit(":", 1)[1]
        if port != "443":
            _refuse("url_non_default_port", "only the implicit or :443 port is allowed")
        netloc_host = netloc[: -len(":443")]
    else:
        netloc_host = netloc
    if netloc_host != netloc_host.lower():
        _refuse("url_non_canonical_host", "base_url host must already be canonical lowercase")
    if parts.query:
        _refuse("url_query", "base_url must not carry a query")
    if parts.fragment:
        _refuse("url_fragment", "base_url must not carry a fragment")
    for segment in parts.path.split("/"):
        if segment in (".", ".."):
            _refuse("url_dot_path_segment", "base_url path carries a dot segment")
    if "%" in parts.path:
        _refuse("url_percent_escape_path", "base_url path carries a percent-escape")
    hostname = canonical_hostname(parts.hostname or "")
    path = parts.path or "/"
    canonical_base = f"https://{hostname}" + ("" if path == "/" else path)
    return TargetURL(raw=raw, hostname=hostname, path=path, canonical_base=canonical_base)


def validate_base_url_against_host(base_url: str, hostname: str) -> TargetURL:
    """Parse plus exact canonical hostname equality with the allowed-host row."""
    parsed = parse_target_base_url(base_url)
    if parsed.hostname != canonical_hostname(hostname):
        _refuse(
            "hostname_mismatch",
            "base_url host must equal the referenced allowed host exactly",
        )
    return parsed


def address_allowed(address: str) -> bool:
    """The shared public-unicast IP policy. Any special range is refused."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv4Address):
        return not any(ip in network for network in _REFUSED_IPV4_NETWORKS)
    if isinstance(ip, ipaddress.IPv6Address):
        if not (
            _GLOBAL_UNICAST_V6_MIN <= ip <= _GLOBAL_UNICAST_V6_MAX
        ):
            return False
        return not any(ip in network for network in _REFUSED_IPV6_NETWORKS)
    return False


def resolve_host_addresses(
    hostname: str, *, timeout_seconds: float = DNS_TIMEOUT_SECONDS
) -> list[str]:
    """Bounded ``getaddrinfo(AF_UNSPEC, SOCK_STREAM)``; never connects.

    Returns the unique resolved address strings. Raises
    ``DiagnosticTargetError("dns_timeout")`` when resolution exceeds the
    bound and ``DiagnosticTargetError("dns_refused")`` when it yields
    nothing. Resolved addresses are never persisted as authority.
    """
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(
            socket.getaddrinfo, hostname, 443, socket.AF_UNSPEC, socket.SOCK_STREAM
        )
        try:
            results = future.result(timeout=timeout_seconds)
        except concurrent.futures.TimeoutError as exc:
            raise DiagnosticTargetError(
                "dns_timeout", f"resolving {hostname} exceeded {timeout_seconds:.0f}s"
            ) from exc
        except socket.gaierror as exc:
            raise DiagnosticTargetError("dns_refused", f"resolving {hostname} failed") from exc
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
    addresses: list[str] = []
    for result in results:
        address = str(result[4][0])
        if address not in addresses:
            addresses.append(address)
    return addresses


def validate_target_dns_addresses(
    hostname: str,
    *,
    resolved: list[str] | None = None,
    timeout_seconds: float = DNS_TIMEOUT_SECONDS,
) -> list[str]:
    """Require >=1 resolution and refuse the name when ANY address is refused."""
    if resolved is None:
        resolved = resolve_host_addresses(hostname, timeout_seconds=timeout_seconds)
    if not resolved:
        raise DiagnosticTargetError("dns_refused", f"no address resolved for {hostname}")
    for address in resolved:
        if not address_allowed(address):
            raise DiagnosticTargetError(
                "dns_refused", f"an address resolved for {hostname} is not allowed"
            )
    return list(resolved)


def validate_credential_env_name(name: str) -> str:
    """Closed credential environment-name set; the value itself is never stored."""
    if name not in CREDENTIAL_ENV_NAMES:
        raise DiagnosticTargetError(
            "credential_env_unknown",
            "credential_env_name must be one of the closed CREDENTIAL_ENV_NAMES set",
        )
    return name


def credential_env_present(
    name: str, environ: Mapping[str, str] | None = None
) -> str:
    """Membership-only presence: never reads or returns a value."""
    if environ is None:
        import os

        environ = os.environ
    try:
        return "yes" if environ.get(name) is not None else "no"
    except Exception:  # pragma: no cover - defensive; never leak a value
        return "unknown"


def _target_is_referenced(target: "DiagnosticTargetLike") -> bool:
    from .models import PlayerSlot

    return PlayerSlot.objects.filter(diagnostic_target_id=target.pk).exists()


class DiagnosticTargetLike(Protocol):
    """Structural view of ``game.models.DiagnosticTarget`` for validation."""

    pk: Any
    base_url: str
    allowed_host_id: int
    allowed_host: Any
    model_id: str
    credential_env_name: str
    is_active: bool
    name: str


def validate_target_save(
    target: DiagnosticTargetLike, *, previous: DiagnosticTargetLike | None
) -> None:
    """Save-time validation; covers ``objects.create()``.

    New or changed connection settings and reactivation re-run the URL policy
    and the bounded DNS check. Deactivation and renaming need no DNS. Once
    any PlayerSlot references the target, ``base_url``, ``allowed_host``,
    ``model_id``, and ``credential_env_name`` freeze; name and activation
    remain editable.
    """
    validate_credential_env_name(target.credential_env_name)
    if not (target.name or "").strip():
        raise DiagnosticTargetError("name_empty", "target name must not be empty")
    if not (target.model_id or "").strip():
        raise DiagnosticTargetError("model_id_empty", "model_id must not be empty")

    previous_snapshot = (
        {
            "base_url": previous.base_url,
            "allowed_host_id": previous.allowed_host_id,
            "model_id": previous.model_id,
            "credential_env_name": previous.credential_env_name,
            "is_active": previous.is_active,
        }
        if previous is not None
        else None
    )

    connection_changed = (
        previous_snapshot is None
        or target.base_url != previous_snapshot["base_url"]
        or target.allowed_host_id != previous_snapshot["allowed_host_id"]
        or target.model_id != previous_snapshot["model_id"]
        or target.credential_env_name != previous_snapshot["credential_env_name"]
    )
    reactivating = (
        previous_snapshot is not None
        and target.is_active
        and not previous_snapshot["is_active"]
    )

    if previous_snapshot is not None and connection_changed:
        if _target_is_referenced(target):
            raise DiagnosticTargetError(
                "frozen",
                "connection settings freeze once a diagnostic seat references the target",
            )

    needs_dns = previous_snapshot is None or connection_changed or reactivating
    parsed = validate_base_url_against_host(
        target.base_url, str(getattr(target.allowed_host, "hostname", "") or "")
    )
    if needs_dns and target.is_active:
        allowed_host = target.allowed_host
        if getattr(allowed_host, "is_active", True) is not True:
            raise DiagnosticTargetError(
                "host_inactive",
                "the referenced allowed host must be active",
            )
        validate_target_dns_addresses(parsed.hostname)
        if connection_changed and _target_is_referenced(target):
            raise DiagnosticTargetError(
                "frozen",
                "connection settings freeze once a diagnostic seat references the target",
            )
