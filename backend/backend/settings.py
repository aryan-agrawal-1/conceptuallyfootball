"""
Django settings for backend project.
"""

import os
from pathlib import Path

from celery.schedules import crontab
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# soccerdata configures logging and cache paths on import; keep everything inside proj
_soccerdata_home = Path(os.environ.get("SOCCERDATA_DIR", str(BASE_DIR / ".soccerdata")))
_soccerdata_home.mkdir(parents=True, exist_ok=True)
(_soccerdata_home / "logs").mkdir(parents=True, exist_ok=True)
os.environ.setdefault("SOCCERDATA_DIR", str(_soccerdata_home))

DEBUG = env_bool("DJANGO_DEBUG", True)

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "django-insecure-local-development-only-statballer-secret-key"
    else:
        raise RuntimeError("DJANGO_SECRET_KEY must be set when DJANGO_DEBUG is disabled.")

ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "django_filters",
    "ingestion",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.gzip.GZipMiddleware",
    "ingestion.middleware.ApiCacheHeadersMiddleware",
    "ingestion.middleware.PublicApiSessionBypassMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.http.ConditionalGetMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "backend.urls"

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

WSGI_APPLICATION = "backend.wsgi.application"

USE_SQLITE = os.environ.get("STATBALLER_USE_SQLITE") == "1"

if USE_SQLITE:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
else:
    database_password = os.environ.get("STATBALLER_DB_PASSWORD")
    if not database_password:
        if DEBUG:
            database_password = "statballer"
        else:
            raise RuntimeError("STATBALLER_DB_PASSWORD must be set when DJANGO_DEBUG is disabled.")
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("STATBALLER_DB_NAME", "statballer"),
            "USER": os.environ.get("STATBALLER_DB_USER", "statballer"),
            "PASSWORD": database_password,
            "HOST": os.environ.get("STATBALLER_DB_HOST", "127.0.0.1"),
            "PORT": os.environ.get("STATBALLER_DB_PORT", "5432"),
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", not DEBUG)
SESSION_COOKIE_SECURE = env_bool("DJANGO_SESSION_COOKIE_SECURE", not DEBUG)
CSRF_COOKIE_SECURE = env_bool("DJANGO_CSRF_COOKIE_SECURE", not DEBUG)
SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_SECURE_HSTS_SECONDS", "0" if DEBUG else "31536000"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", not DEBUG)
SECURE_HSTS_PRELOAD = env_bool("DJANGO_SECURE_HSTS_PRELOAD", False)
if env_bool("DJANGO_TRUST_X_FORWARDED_PROTO", False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://127.0.0.1:6379/0")
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", CELERY_BROKER_URL)
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 60 * 60
CELERY_TASK_ROUTES = {
    "ingestion.tasks.task_plan_daily_refresh": {"queue": "ingestion-planner"},
    "ingestion.tasks.task_refresh_competition_season_item": {"queue": "ingestion"},
    "ingestion.tasks.task_finalize_daily_refresh_batch": {"queue": "ingestion"},
}
CELERY_BEAT_SCHEDULE = {
    "plan-daily-refresh": {
        "task": "ingestion.tasks.task_plan_daily_refresh",
        "schedule": crontab(minute="*/15"),
    },
}

REST_FRAMEWORK = {
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.AllowAny",
    ],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "regression_fit": os.environ.get("STATBALLER_REGRESSION_FIT_RATE", "30/min"),
    },
}

STATBALLER_INGEST_MIN_ROWS = int(os.environ.get("STATBALLER_INGEST_MIN_ROWS", "200"))

# I got ip blocked lets do this instead
STATBALLER_SOFASCORE_REQUEST_DELAY_SECONDS = float(
    os.environ.get("STATBALLER_SOFASCORE_REQUEST_DELAY_SECONDS", "1.5" if DEBUG else "4.0")
)
STATBALLER_SOFASCORE_RETRY_BASE_SLEEP_SECONDS = float(
    os.environ.get("STATBALLER_SOFASCORE_RETRY_BASE_SLEEP_SECONDS", "8.0")
)
STATBALLER_BATCH_SLICE_SLEEP_SECONDS = float(
    os.environ.get("STATBALLER_BATCH_SLICE_SLEEP_SECONDS", "20.0")
)
STATBALLER_BATCH_LEAGUE_SLEEP_SECONDS = float(
    os.environ.get("STATBALLER_BATCH_LEAGUE_SLEEP_SECONDS", "120.0")
)
STATBALLER_DAILY_REFRESH_ENABLED = os.environ.get("STATBALLER_DAILY_REFRESH_ENABLED", "1") == "1"
STATBALLER_DAILY_REFRESH_START_HOUR = int(os.environ.get("STATBALLER_DAILY_REFRESH_START_HOUR", "1"))
STATBALLER_DAILY_REFRESH_END_HOUR = int(os.environ.get("STATBALLER_DAILY_REFRESH_END_HOUR", "7"))
STATBALLER_DAILY_REFRESH_TIME_ZONE = os.environ.get(
    "STATBALLER_DAILY_REFRESH_TIME_ZONE",
    "Europe/London",
)
STATBALLER_DAILY_REFRESH_MIN_LEAGUE_DELAY_SECONDS = int(
    os.environ.get("STATBALLER_DAILY_REFRESH_MIN_LEAGUE_DELAY_SECONDS", "600")
)
STATBALLER_DAILY_REFRESH_MAX_LEAGUE_DELAY_SECONDS = int(
    os.environ.get("STATBALLER_DAILY_REFRESH_MAX_LEAGUE_DELAY_SECONDS", "1500")
)
STATBALLER_SOFASCORE_DAILY_REQUEST_CAP = int(
    os.environ.get("STATBALLER_SOFASCORE_DAILY_REQUEST_CAP", "1000")
)
STATBALLER_SOFASCORE_PROXY_URL = os.environ.get("STATBALLER_SOFASCORE_PROXY_URL", "")
STATBALLER_HTTP_PROXY_URL = os.environ.get("STATBALLER_HTTP_PROXY_URL", "")

STATBALLER_REEP_DATA_PATH = os.environ.get("STATBALLER_REEP_DATA_PATH", "")
STATBALLER_REEP_CSV_DIR = os.environ.get("STATBALLER_REEP_CSV_DIR", "")
STATBALLER_HTTP_USER_AGENT = os.environ.get(
    "STATBALLER_HTTP_USER_AGENT",
    "Mozilla/5.0 (compatible; StatballerIngestion/1.0; +https://example.invalid)",
)

# When True, Understat ingestion bypasses soccerdata disk cache (live scrape each run).
STATBALLER_SOCCERDATA_NO_CACHE = os.environ.get("STATBALLER_SOCCERDATA_NO_CACHE", "1") == "1"
