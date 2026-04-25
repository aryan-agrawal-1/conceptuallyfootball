"""
Django settings for backend project.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# soccerdata configures logging and cache paths on import; keep everything inside the project.
_soccerdata_home = Path(os.environ.get("SOCCERDATA_DIR", str(BASE_DIR / ".soccerdata")))
_soccerdata_home.mkdir(parents=True, exist_ok=True)
(_soccerdata_home / "logs").mkdir(parents=True, exist_ok=True)
os.environ.setdefault("SOCCERDATA_DIR", str(_soccerdata_home))

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-s(ck5)&!!=m)#-7e&!#=g4ty(42q26%+3572p3&6$49w-^^_+0",
)

DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"

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
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
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
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("STATBALLER_DB_NAME", "statballer"),
            "USER": os.environ.get("STATBALLER_DB_USER", "statballer"),
            "PASSWORD": os.environ.get("STATBALLER_DB_PASSWORD", "statballer"),
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
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://127.0.0.1:6379/0")
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", CELERY_BROKER_URL)
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 60 * 60

REST_FRAMEWORK = {
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.AllowAny",
    ],
}

STATBALLER_INGEST_MIN_ROWS = int(os.environ.get("STATBALLER_INGEST_MIN_ROWS", "200"))

STATBALLER_REEP_DATA_PATH = os.environ.get("STATBALLER_REEP_DATA_PATH", "")
STATBALLER_REEP_CSV_DIR = os.environ.get("STATBALLER_REEP_CSV_DIR", "")
STATBALLER_HTTP_USER_AGENT = os.environ.get(
    "STATBALLER_HTTP_USER_AGENT",
    "Mozilla/5.0 (compatible; StatballerIngestion/1.0; +https://example.invalid)",
)

# When True, Understat ingestion bypasses soccerdata disk cache (live scrape each run).
STATBALLER_SOCCERDATA_NO_CACHE = os.environ.get("STATBALLER_SOCCERDATA_NO_CACHE", "1") == "1"
