from pathlib import Path
from dotenv import load_dotenv
import os

BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env only if exists (VPS)
dotenv_path = BASE_DIR / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path)
    IS_PRODUCTION = True
else:
    IS_PRODUCTION = False

# -----------------------
# SECURITY
# -----------------------
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-unsafe")

DEBUG = False if IS_PRODUCTION else True

if IS_PRODUCTION:
    raw_hosts = os.getenv("ALLOWED_HOSTS", "")
    ALLOWED_HOSTS = [h.strip() for h in raw_hosts.split(",") if h.strip()]
else:
    ALLOWED_HOSTS = ["127.0.0.1", "localhost"]

# -----------------------
# INSTALLED APPS
# -----------------------
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'shop',

    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
]

# -----------------------
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    "allauth.account.middleware.AccountMiddleware",
]

ROOT_URLCONF = 'e_shop.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': ['templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'shop.context_processors.cart_items_count',
            ],
        },
    },
]

WSGI_APPLICATION = 'e_shop.wsgi.application'

# -----------------------
# DATABASE SWITCH
# -----------------------
if IS_PRODUCTION:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("DB_NAME"),
            "USER": os.getenv("DB_USER"),
            "PASSWORD": os.getenv("DB_PASS"),
            "HOST": os.getenv("DB_HOST"),
            "PORT": os.getenv("DB_PORT"),
        }
    }
else:
    # LOCAL DEVELOPMENT DATABASE
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': 'fnfbazar',
            'USER': 'postgres',
            'PASSWORD': 'admin',
            'HOST': 'localhost',
            'PORT': '5432',
        }
    }

# -----------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# -----------------------
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# -----------------------
LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'

# -----------------------
# SSLCOMMERZ
SSLCOMMERZ_STORE_ID = os.getenv("SSLCOMMERZ_STORE_ID", "")
SSLCOMMERZ_STORE_PASSWORD = os.getenv("SSLCOMMERZ_STORE_PASSWORD", "")
SSLCOMMERZ_PAYMENT_URL = os.getenv("SSLCOMMERZ_PAYMENT_URL", "")
SSLCOMMERZ_VALIDATION_URL = os.getenv("SSLCOMMERZ_VALIDATION_URL", "")

# -----------------------
# EMAIL SETTINGS
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", 587))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "True") == "True"
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
