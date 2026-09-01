"""DRF/SimpleJWT glue for django-axes.

AxesMiddleware must remain last in MIDDLEWARE (axes.W002). This middleware
stays immediately before it: it copies lockout state from the DRF Request
wrapper onto the Django request, and resets failure counters on a successful
API login because SimpleJWT does not fire user_logged_in.
"""

from __future__ import annotations


def username_from_auth_request(request: object) -> str | None:
    post = getattr(request, "POST", None)
    if post is not None:
        raw = post.get("username")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    try:
        import json

        from django.http.request import RawPostDataException

        body = request.body  # type: ignore[attr-defined]
    except (AttributeError, OSError, RawPostDataException):
        return None
    if not isinstance(body, (bytes, bytearray)) or not body:
        return None
    try:
        parsed = json.loads(bytes(body).decode("utf-8"))
    except (UnicodeDecodeError, ValueError, TypeError):
        return None
    if isinstance(parsed, dict):
        raw = parsed.get("username")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return None


def propagate_axes_lockout_to_django_request(
    sender: object,
    request: object,
    **kwargs: object,
) -> None:
    """SimpleJWT passes the DRF Request into authenticate(); axes sets the
    lockout flag on that wrapper. AxesMiddleware reads the Django HttpRequest.
    """
    django_request = getattr(request, "_request", None)
    if django_request is None:
        return
    setattr(django_request, "axes_locked_out", True)
    credentials = getattr(request, "axes_credentials", None)
    if credentials is not None:
        setattr(django_request, "axes_credentials", credentials)


class AxesDrfLockoutFlagMiddleware:
    """DRF/SimpleJWT glue for axes: copy lockout onto the Django request, and
    reset counters on a successful API login (SimpleJWT does not fire
    user_logged_in, so AXES_RESET_ON_SUCCESS alone would miss that path).
    """

    def __init__(self, get_response: object) -> None:
        from axes.signals import user_locked_out

        user_locked_out.connect(
            propagate_axes_lockout_to_django_request,
            dispatch_uid="libretiles_axes_drf_lockout",
        )
        self.get_response = get_response

    def __call__(self, request: object) -> object:
        path = str(getattr(request, "path_info", "") or "")
        login_username = None
        if path.rstrip("/") == "/api/auth/login":
            login_username = username_from_auth_request(request)
        response = self.get_response(request)  # type: ignore[operator]
        if (
            login_username
            and getattr(response, "status_code", None) == 200
            and path.rstrip("/") == "/api/auth/login"
        ):
            meta = getattr(request, "META", {})
            ip_address = meta.get("REMOTE_ADDR") if isinstance(meta, dict) else None
            if isinstance(ip_address, str) and ip_address:
                from axes.handlers.proxy import AxesProxyHandler

                AxesProxyHandler.reset_attempts(
                    ip_address=ip_address,
                    username=login_username,
                    ip_or_username=False,
                )
        return response
