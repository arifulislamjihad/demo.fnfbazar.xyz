from pathlib import Path
import os
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# --------------------------
# LOAD ENV FILE
# --------------------------
env_file = BASE_DIR / ".env"
if env_file.exists():
    load_dotenv(env_file)

DJANGO_ENV = os.getenv("DJANGO_ENV", "development")
IS_PRODUCTION = DJANGO_ENV == "production"

# --------------------------
# SECURITY
# --------------------------
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")

DEBUG = not IS_PRODUCTION

# --------------------------
# ALLOWED HOSTS
# --------------------------
raw_hosts = os.getenv("ALLOWED_HOSTS", "")
env_hosts = [h.strip() for h in raw_hosts.split(",") if h.strip()]

DOCKER_HOSTS = [
    "fnfbazar_django",
    "localhost",
    "127.0.0.1",
]

ALLOWED_HOSTS = list(set(env_hosts + DOCKER_HOSTS))

print("🔵 ENV:", DJANGO_ENV)
print("🔵 DEBUG:", DEBUG)
print("🔵 ALLOWED_HOSTS:", ALLOWED_HOSTS)

# --------------------------
# HTTPS / PROXY FIX
# --------------------------
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

CSRF_TRUSTED_ORIGINS = [
    "https://shop.fnfbazar.xyz",
    "https://www.shop.fnfbazar.xyz",
]

# --------------------------
# INSTALLED APPS
# --------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    "shop",

    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
]

# --------------------------
# MIDDLEWARE
# --------------------------
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",

    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",

    "allauth.account.middleware.AccountMiddleware",
]

ROOT_URLCONF = "e_shop.urls"

# --------------------------
# TEMPLATES
# --------------------------
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "shop.context_processors.cart_items_count",
                "shop.context_processors.site_settings",
                "shop.context_processors.facebook_pixel",   # FB Pixel context
            ],
        },
    },
]

WSGI_APPLICATION = "e_shop.wsgi.application"

# --------------------------
# DATABASE
# --------------------------
if IS_PRODUCTION:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("DB_NAME"),
            "USER": os.getenv("DB_USER"),
            "PASSWORD": os.getenv("DB_PASS"),
            "HOST": os.getenv("DB_HOST"),
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

# --------------------------
# STATIC & MEDIA
# --------------------------
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# --------------------------
# AUTH
# --------------------------
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"

# --------------------------
# SSLCOMMERZ
# --------------------------
SSLCOMMERZ_STORE_ID = os.getenv("SSLCOMMERZ_STORE_ID", "")
SSLCOMMERZ_STORE_PASSWORD = os.getenv("SSLCOMMERZ_STORE_PASSWORD", "")
SSLCOMMERZ_PAYMENT_URL = os.getenv("SSLCOMMERZ_PAYMENT_URL", "")
SSLCOMMERZ_VALIDATION_URL = os.getenv("SSLCOMMERZ_VALIDATION_URL", "")

# --------------------------
# STEADFAST COURIER
# --------------------------
# এখানে তুমি যেভাবে রেখে ছিলে, সেভাবেই রাখলাম
if IS_PRODUCTION:
    # production এ চাইলে env থেকে নাও (এখন key নাম হিসেবে আগের string-ই আছে)
    STEADFAST_API_KEY = os.getenv("3k5v35is1nmksdywmdgwgkmweya6b1zr", "")
    STEADFAST_SECRET_KEY = os.getenv("isptxoqld14x3jtf3rzrvip8", "")
else:
    # local/dev এর জন্য সরাসরি string
    STEADFAST_API_KEY = "3k5v35is1nmksdywmdgwgkmweya6b1zr"
    STEADFAST_SECRET_KEY = "isptxoqld14x3jtf3rzrvip8"

STEADFAST_BASE_URL = os.getenv(
    "STEADFAST_BASE_URL",
    "https://portal.packzy.com/api/v1",
)

# --------------------------
# FACEBOOK PIXEL / CAPI
# --------------------------
# তোমার Facebook Dataset / Pixel ID
FACEBOOK_PIXEL_ID = "1769049247131500"

# Conversions API er Access Token
FACEBOOK_CAPI_ACCESS_TOKEN = "EAARogZCQ2xV8BQGvEfSfv4FA71r6WZC8iZAExSZA1cmlQ2DNxRRxRJEjfeVUScD8tu5ZBzpAp4NsHQolzK9X6P5FemS5OpoLAOIyJbahuLPT5fvrsxvkWZAEJ7oUoNH8AnqXN9Qs44NrxI203w4ktVELeXF4EiRW8xSzWoZACNVL2nPjIDYHAG2AHiK7SkuhBWxZBwZDZD"

# --------------------------
# EMAIL SETTINGS
# --------------------------
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.getenv("EMAIL_HOST")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", 587))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "True") == "True"
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
