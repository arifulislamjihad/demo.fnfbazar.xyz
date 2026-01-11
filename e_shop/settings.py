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

# [IMPORTANT] Ensure DEBUG is False in Production
DEBUG = not IS_PRODUCTION

# --------------------------
# ALLOWED HOSTS
# --------------------------
raw_hosts = os.getenv("ALLOWED_HOSTS", "")
env_hosts = [h.strip() for h in raw_hosts.split(",") if h.strip()]

DOCKER_HOSTS = [
    "fnfbazar_django",
    "aboroni_django",
    "localhost",
    "127.0.0.1",
    "entertaining-hyperemotional-tandy.ngrok-free.dev",
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

raw_csrf = os.getenv("CSRF_TRUSTED_ORIGINS", "")
if raw_csrf:
    CSRF_TRUSTED_ORIGINS = [o.strip() for o in raw_csrf.split(",") if o.strip()]
else:
    CSRF_TRUSTED_ORIGINS = []

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

    "django_admin_listfilter_dropdown",
    
    # [FEATURE] CKEditor for Rich Text & Media Library
    "ckeditor",
    "ckeditor_uploader",

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
# ... (Baki sob code same thakbe)

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
                # Custom Processors
                "shop.context_processors.cart_items_count",
                "shop.context_processors.site_settings",
                "shop.context_processors.facebook_pixel",
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

# [FEATURE] CKEDITOR CONFIGURATION
CKEDITOR_UPLOAD_PATH = "uploads/"
CKEDITOR_IMAGE_BACKEND = "pillow"
CKEDITOR_BROWSE_SHOW_DIRS = True 
CKEDITOR_RESTRICT_BY_USER = True 

CKEDITOR_CONFIGS = {
    'default': {
        'toolbar': 'full',
        'height': 400,
        'width': '100%',
        'tabSpaces': 4,
        'extraPlugins': ','.join([
            'uploadimage', 
            'div',
            'autolink',
            'autoembed',
            'embedsemantic',
            'autogrow',
            'widget',
            'lineutils',
            'clipboard',
            'dialog',
            'dialogui',
            'elementspath'
        ]),
    },
}

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
if IS_PRODUCTION:
    # [FIXED] os.getenv Key name fixed. Previous code had the Value as Key.
    STEADFAST_API_KEY = os.getenv("STEADFAST_API_KEY", "")
    STEADFAST_SECRET_KEY = os.getenv("STEADFAST_SECRET_KEY", "")
else:
    STEADFAST_API_KEY = "3k5v35is1nmksdywmdgwgkmweya6b1zr"
    STEADFAST_SECRET_KEY = "isptxoqld14x3jtf3rzrvip8"

STEADFAST_BASE_URL = os.getenv(
    "STEADFAST_BASE_URL",
    "https://portal.packzy.com/api/v1",
)

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