import os
from dotenv import load_dotenv

load_dotenv()  # Loads variables from .env into os.environ

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Config:
    """Application configuration loaded from environment variables."""

    # Signing key for session cookies. NEVER hardcode this in real apps.
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        raise RuntimeError(
            "SECRET_KEY is not set. Create a .env file with "
            "SECRET_KEY=<your-random-hex-string>."
        )

    # Absolute path so the DB always lands in the project root's instance/
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        f'sqlite:///{os.path.join(BASE_DIR, "instance", "cms.db")}'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Business defaults
    DEFAULT_DUE_DAYS = 30
    INVOICE_PREFIX = 'INV-'

    # Session cookie hardening
    SESSION_COOKIE_HTTPONLY = True   # JS can't read the cookie (blocks XSS theft)
    SESSION_COOKIE_SAMESITE = 'Lax'  # Blocks most CSRF attacks
    # SESSION_COOKIE_SECURE = True   # Uncomment in production (requires HTTPS)