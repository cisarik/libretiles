"""Django settings for Libre Tiles backend.

Admin-first philosophy: all game configuration (AI models, variants)
is managed through Django Admin at /admin/.
"""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

_PUBLIC_INSECURE_SECRET_KEY = "insecure-dev-key-change-in-production"
_SECRET_KEY_MIN_LENGTH = 50
_SECRET_KEY_MIN_UNIQUE_CHARACTERS = 5
_SECRET_KEY_INSECURE_PREFIX = "django-insecure-"
_HSTS_SECONDS = 31536000


def _require_secret_key() -> str:
    raw = os.getenv("DJANGO_SECRET_KEY")
    if raw is None:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY is not set. Refusing to start without an explicit secret."
        )
    key = raw.strip()
    if not key:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY is empty or whitespace-only. Refusing to start."
        )
    if key == _PUBLIC_INSECURE_SECRET_KEY:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY matches the public insecure fallback. Refusing to start."
        )
    if (
        len(key) < _SECRET_KEY_MIN_LENGTH
        or len(set(key)) < _SECRET_KEY_MIN_UNIQUE_CHARACTERS
        or key.startswith(_SECRET_KEY_INSECURE_PREFIX)
    ):
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY is too weak. Use at least 50 characters with "
            "5 unique characters, and do not use the django-insecure- prefix."
        )
    return key


def _env_flag(name: str, *, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("true", "1", "yes")


def _num_proxies() -> int:
    # DRF BaseThrottle.get_ident: NUM_PROXIES=0 returns REMOTE_ADDR even when
    # X-Forwarded-For is present. That is the safe default. A positive value
    # is the count of trusted reverse proxies; DRF then takes that many
    # addresses from the right of X-Forwarded-For. The correct non-zero value
    # is a deployment fact this repository does not contain.
    #
    # django-axes independently keys on REMOTE_ADDR because ipware is not
    # installed. The two brakes must agree: if DRF trusted a client-supplied
    # header while axes used the socket address, a username spray would
    # bypass the unauthenticated throttle.
    #
    # Trade-off: with NUM_PROXIES=0 behind a real reverse proxy, every client
    # shares the proxy's socket address and IP-keyed throttles become
    # effectively global. That over-throttles (fails safe) rather than
    # under-throttles. Configuring the proxy itself is host territory.
    #
    # Invalid DJANGO_NUM_PROXIES values refuse to start. Silently falling
    # through to DRF's default NUM_PROXIES=None would key buckets on the raw
    # client-supplied header.
    raw = os.getenv("DJANGO_NUM_PROXIES")
    if raw is None or not raw.strip():
        return 0
    try:
        value = int(raw.strip())
    except ValueError:
        raise ImproperlyConfigured(
            "DJANGO_NUM_PROXIES must be a non-negative integer. "
            "0 keys unauthenticated throttles on REMOTE_ADDR; a positive "
            "value is the trusted reverse-proxy count."
        ) from None
    if value < 0:
        raise ImproperlyConfigured(
            "DJANGO_NUM_PROXIES must be a non-negative integer. "
            "0 keys unauthenticated throttles on REMOTE_ADDR; a positive "
            "value is the trusted reverse-proxy count."
        )
    return value


def _allowed_hosts(*, debug: bool) -> list[str]:
    raw = os.getenv("DJANGO_ALLOWED_HOSTS")
    if raw is None or not raw.strip():
        if debug:
            return ["localhost", "127.0.0.1"]
        raise ImproperlyConfigured(
            "DJANGO_ALLOWED_HOSTS must be set explicitly when DEBUG is false."
        )
    hosts = [part.strip() for part in raw.split(",") if part.strip()]
    if not debug and (not hosts or "*" in hosts):
        raise ImproperlyConfigured(
            "DJANGO_ALLOWED_HOSTS must be an explicit host list without wildcards "
            "when DEBUG is false."
        )
    return hosts


SECRET_KEY = _require_secret_key()
DEBUG = _env_flag("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS: list[str] = _allowed_hosts(debug=DEBUG)

INSTALLED_APPS = [
    "daphne",
    "channels",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "axes",
    # Local apps
    "accounts",
    "catalog",
    "game",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Copy lockout state from the DRF Request wrapper onto the Django request
    # before AxesMiddleware (which must stay last for axes.W002).
    "config.middleware.AxesDrfLockoutFlagMiddleware",
    "axes.middleware.AxesMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# Database — PostgreSQL in production, SQLite for dev/test convenience
_DB_ENGINE = os.getenv("DB_ENGINE", "sqlite3")
DATABASES: dict[str, dict[str, str | Path]]
if _DB_ENGINE == "postgresql":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("DB_NAME", "libretiles"),
            "USER": os.getenv("DB_USER", "libretiles"),
            "PASSWORD": os.getenv("DB_PASSWORD", "libretiles"),
            "HOST": os.getenv("DB_HOST", "localhost"),
            "PORT": os.getenv("DB_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_USER_MODEL = "accounts.User"

# AxesStandaloneBackend is a lockout gate only; it does not authenticate.
# It must be first so a locked (username, IP) pair never reaches ModelBackend.
# ModelBackend remains the real password checker.
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
LANGUAGES = [
    ("en", "English"),
    ("sk", "Slovak"),
    ("cs", "Czech"),
    ("pl", "Polish"),
]
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# CORS — allow Vercel frontend
CORS_ALLOWED_ORIGINS: list[str] = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000").split(",")
    if origin.strip()
]
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_ALL_ORIGINS = DEBUG
# Retry-After is not a CORS-safelisted response header, so a cross-origin
# frontend cannot read it at all unless it is exposed explicitly. The client
# prefers this numeric header over parsing a localized 429 body (uii-01-F01).
CORS_EXPOSE_HEADERS: list[str] = ["Retry-After"]

# HTTPS flags follow DEBUG so plain local HTTP still works.
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = not DEBUG
SECURE_HSTS_SECONDS = _HSTS_SECONDS if not DEBUG else 0
# orch-02-D11. A max-age without includeSubDomains leaves every subdomain
# reachable over plain HTTP, which is the hole HSTS exists to close, and Django's
# own deployment check security.W005 says so.
#
# SECURE_HSTS_PRELOAD is deliberately NOT set. Cooperator decision 5. Preloading
# is submitted to a browser-vendor list and is effectively irreversible on the
# timescale of a mistake, so Django's security.W021 warning is an ACCEPTED
# residual here rather than something to silence. test_security_settings.py
# asserts that W021 is still emitted.
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG

# Framework defaults made explicit so a later edit cannot drop them silently.
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

_LOCMEM_CACHE_BACKEND = "django.core.cache.backends.locmem.LocMemCache"
_REDIS_CACHE_BACKEND = "django.core.cache.backends.redis.RedisCache"
_SHARED_CACHE_SCHEMES = ("redis://", "rediss://")


def _default_cache(*, debug: bool) -> dict[str, str]:
    # LocMem is correct in development: each process has its own throttle
    # budget, Redis is not required for AI-only boot, and counters resetting
    # on restart is acceptable. It is not a shared store. Production must
    # fail closed rather than silently multiply the brake by worker count.
    if debug:
        return {
            "BACKEND": _LOCMEM_CACHE_BACKEND,
            "LOCATION": "libretiles-default",
        }
    dedicated = os.getenv("DJANGO_THROTTLE_CACHE_URL")
    fallback = os.getenv("REDIS_URL")
    if dedicated is not None and dedicated.strip():
        location = dedicated.strip()
        source = "DJANGO_THROTTLE_CACHE_URL"
    elif fallback is not None and fallback.strip():
        location = fallback.strip()
        source = "REDIS_URL"
    else:
        raise ImproperlyConfigured(
            "DJANGO_THROTTLE_CACHE_URL or REDIS_URL must be set to a redis:// "
            "or rediss:// URL when DEBUG is false. LocMemCache is per-process "
            "and is not a shared throttle store."
        )
    if not location.startswith(_SHARED_CACHE_SCHEMES):
        raise ImproperlyConfigured(
            f"{source} must be a redis:// or rediss:// URL when DEBUG is false; "
            "per-process caches are not allowed. Set DJANGO_THROTTLE_CACHE_URL."
        )
    return {
        "BACKEND": _REDIS_CACHE_BACKEND,
        "LOCATION": location,
    }


CACHES = {"default": _default_cache(debug=DEBUG)}

# DRF
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "accounts.authentication.PasswordAwareJWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        # IP-keyed coarse anti-bulk rates. Per-account brute-force is axes
        # (8 failures / 30 min for one username+IP pair). A same-NAT demo of
        # two browser profiles + an interviewer is ~16 logins and ~12
        # registrations; axes 8 is well below auth_login 60 so a targeted
        # account locks first.
        "auth_register": "20/hour",
        "auth_login": "60/hour",
        "auth_refresh": "60/hour",
        "auth_change_password": "5/hour",
        "auth_me": "200/hour",
        "ai_context": "200/hour",
    },
    # See _num_proxies: 0 binds get_ident to REMOTE_ADDR; override via
    # DJANGO_NUM_PROXIES when a trusted proxy count is known.
    "NUM_PROXIES": _num_proxies(),
}

# JWT
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=2),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "TOKEN_REFRESH_SERIALIZER": "accounts.serializers.PasswordAwareTokenRefreshSerializer",
}

# django-axes 8.3.1. Setting names and defaults taken from axes/conf.py of the
# installed package. The package default lockout is IP-only (["ip_address"]);
# that would lock every account behind one NAT, so it is overridden.
AXES_FAILURE_LIMIT = 8
AXES_COOLOFF_TIME = timedelta(minutes=30)
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_PARAMETERS: list[list[str]] = [["username", "ip_address"]]
AXES_HTTP_RESPONSE_CODE = 429
AXES_ENABLE_ADMIN = True

REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [REDIS_URL]},
    }
}
GAME_WS_TICKET_MAX_AGE_SECONDS = int(os.getenv("GAME_WS_TICKET_MAX_AGE_SECONDS", "10"))

# Game assets
ASSETS_DIR = BASE_DIR / "assets"
PREMIUMS_PATH = ASSETS_DIR / "premiums.json"
VARIANTS_DIR = ASSETS_DIR / "variants"
DICTS_DIR = ASSETS_DIR / "dicts"
PRIMARY_DICTIONARY_PATH = DICTS_DIR / os.getenv("PRIMARY_DICTIONARY_FILE", "collins2019.txt")

# AI budget (unified, same as scrabgpt)
AI_MOVE_MAX_OUTPUT_TOKENS = int(os.getenv("AI_MOVE_MAX_OUTPUT_TOKENS", "15000"))
AI_MOVE_TIMEOUT_SECONDS = int(os.getenv("AI_MOVE_TIMEOUT_SECONDS", "120"))

# When false, /api/catalog/models/ returns the curated bootstrap pairs only.
# When true, returns the four newest eligible OpenRouter models plus seeded NIM.
DYNAMIC_FREE_MODEL_CATALOG_ENABLED = os.getenv(
    "DYNAMIC_FREE_MODEL_CATALOG_ENABLED", "false"
).lower() in ("true", "1", "yes")

# When false, manage.py purge_legacy_game_state refuses to delete any row
# unless the five development game-state tables are already empty (documented
# no-op). When true, that one-time development purge empties those five
# tables only. Fail-closed: the default is false. A pre-existing .env
# overrides code defaults and is read once at process start.
ALLOW_DESTRUCTIVE_GAME_STATE_RESET = _env_flag(
    "ALLOW_DESTRUCTIVE_GAME_STATE_RESET",
    default=False,
)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "console": {
            "format": "{levelname} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "console",
        },
    },
    "loggers": {
        "game": {
            "handlers": ["console"],
            "level": "INFO" if DEBUG else "WARNING",
            "propagate": False,
        },
        "accounts": {
            "handlers": ["console"],
            "level": "INFO" if DEBUG else "WARNING",
            "propagate": False,
        },
        "catalog": {
            "handlers": ["console"],
            "level": "INFO" if DEBUG else "WARNING",
            "propagate": False,
        },
        "config": {
            "handlers": ["console"],
            "level": "INFO" if DEBUG else "WARNING",
            "propagate": False,
        },
    },
}
