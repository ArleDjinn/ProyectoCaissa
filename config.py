import os


def _env_bool(key: str, default: bool = False) -> bool:
    value = os.environ.get(key)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "t", "yes", "y"}


BASE_DIR = os.path.abspath(os.path.dirname(__file__))

_DEFAULT_PRODUCTION = os.environ.get("FLASK_ENV") == "production"

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")

    SQLALCHEMY_DATABASE_URI = (
        os.environ.get("SQLALCHEMY_DATABASE_URI")
        or os.environ.get("DATABASE_URL")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    MAIL_PROVIDER = os.environ.get("MAIL_PROVIDER")
    MAIL_SERVER = os.environ.get("MAIL_SERVER")
    MAIL_PORT = (
        int(os.environ.get("MAIL_PORT")) if os.environ.get("MAIL_PORT") else None
    )
    MAIL_USE_TLS = _env_bool("MAIL_USE_TLS", False)
    MAIL_USE_SSL = _env_bool("MAIL_USE_SSL", False)

    # Webpay
    TBK_ENV = os.environ.get("TBK_ENV", "integration")
    TBK_COMMERCE_CODE = os.environ.get("TBK_COMMERCE_CODE")
    TBK_API_KEY = os.environ.get("TBK_API_KEY")

    # Google OAuth
    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
    GOOGLE_DISCOVERY_URL = os.environ.get(
        "GOOGLE_DISCOVERY_URL",
        "https://accounts.google.com/.well-known/openid-configuration",
    )
    GOOGLE_AUTHORIZATION_ENDPOINT = os.environ.get(
        "GOOGLE_AUTHORIZATION_ENDPOINT",
        "https://accounts.google.com/o/oauth2/v2/auth",
    )
    GOOGLE_TOKEN_ENDPOINT = os.environ.get(
        "GOOGLE_TOKEN_ENDPOINT",
        "https://oauth2.googleapis.com/token",
    )
    GOOGLE_USERINFO_ENDPOINT = os.environ.get(
        "GOOGLE_USERINFO_ENDPOINT",
        "https://openidconnect.googleapis.com/v1/userinfo",
    )
    GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI")
    GOOGLE_HTTP_TIMEOUT = int(os.environ.get("GOOGLE_HTTP_TIMEOUT", 10))

    SESSION_COOKIE_DOMAIN = os.environ.get(
        "SESSION_COOKIE_DOMAIN", ".ajedrezrecreativo.cl"
    )
    SESSION_COOKIE_SECURE = _env_bool(
        "SESSION_COOKIE_SECURE", _DEFAULT_PRODUCTION
    )
    SESSION_COOKIE_SAMESITE = os.environ.get(
        "SESSION_COOKIE_SAMESITE",
        "None" if SESSION_COOKIE_SECURE else "Lax",
    )

    # Tokens
    INITIAL_PASSWORD_TOKEN_SALT = os.environ.get(
        "INITIAL_PASSWORD_TOKEN_SALT", "initial-password"
    )
    INITIAL_PASSWORD_TOKEN_MAX_AGE = int(
        os.environ.get("INITIAL_PASSWORD_TOKEN_MAX_AGE", 60 * 60 * 24 * 7)
    )


if Config.MAIL_PROVIDER == "google_workspace":
    Config.MAIL_SERVER = Config.MAIL_SERVER or "smtp.gmail.com"
    Config.MAIL_PORT = Config.MAIL_PORT or 465
    Config.MAIL_USE_TLS = _env_bool("MAIL_USE_TLS", False)
    Config.MAIL_USE_SSL = _env_bool("MAIL_USE_SSL", True)
