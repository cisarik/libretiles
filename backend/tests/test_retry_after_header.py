"""The 429 wait time travels as a numeric header, not as localized prose.

uii-01-F01. `frontend/src/lib/api.ts` used to read the wait time by matching
`/(\\d+)\\s+seconds/i` against Django's English 429 body. That works today only
because DRF ships no translation for the wait suffix, which R7 measured and
`test_locale_resolution.py` pins. These tests cover the durable channel instead:
DRF's own `Retry-After` header, and the CORS exposure without which a
cross-origin browser cannot read it.
"""

from __future__ import annotations

from django.conf import settings
from rest_framework.exceptions import Throttled
from rest_framework.views import exception_handler


def test_drf_sets_a_numeric_retry_after_header_on_throttle() -> None:
    response = exception_handler(Throttled(wait=3300), {})
    assert response is not None
    assert response.status_code == 429
    assert response["Retry-After"] == "3300"
    # The value must be a bare integer of seconds, because the client parses it
    # with Number(). An HTTP-date would silently fall back to prose parsing.
    assert response["Retry-After"].isdigit()


def test_throttle_without_a_known_wait_omits_the_header() -> None:
    """No `wait` means no header, and the client must survive that."""
    response = exception_handler(Throttled(), {})
    assert response is not None
    assert response.status_code == 429
    assert "Retry-After" not in response


def test_retry_after_is_exposed_to_cross_origin_readers() -> None:
    """Without this the header exists on the wire and JS cannot see it.

    django-cors-headers emits `Access-Control-Expose-Headers` only when
    `CORS_EXPOSE_HEADERS` is non-empty (corsheaders/middleware.py:120-122), and
    the frontend on :3000 is cross-origin to Django on :8000.
    """
    exposed = [name.lower() for name in settings.CORS_EXPOSE_HEADERS]
    assert "retry-after" in exposed
