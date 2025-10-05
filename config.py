import os


def _env_bool(key: str, default: bool = False) -> bool:
    value = os.environ.get(key)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "t", "yes", "y"}


BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")

    SQLALCHEMY_DATABASE_URI = (
        os.environ.get("SQLALCHEMY_DATABASE_URI")
        or os.environ.get("DATABASE_URL")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Webpay
    TBK_ENV = os.environ.get("TBK_ENV", "integration")
    TBK_COMMERCE_CODE = os.environ.get("TBK_COMMERCE_CODE")
    TBK_API_KEY = os.environ.get("TBK_API_KEY")

    # Mail
    _mail_provider = os.environ.get("MAIL_PROVIDER", "default").lower()
    if _mail_provider in {"google_workspace", "gmail"}:
        _mail_defaults = {
            "MAIL_SERVER": "smtp.gmail.com",
            "MAIL_PORT": 587,
            "MAIL_USE_TLS": True,
            "MAIL_USE_SSL": False,
        }
    else:
        _mail_defaults = {
            "MAIL_SERVER": "localhost",
            "MAIL_PORT": 25,
            "MAIL_USE_TLS": False,
            "MAIL_USE_SSL": False,
        }

    MAIL_SERVER = os.environ.get("MAIL_SERVER", _mail_defaults["MAIL_SERVER"])
    MAIL_PORT = int(os.environ.get("MAIL_PORT", _mail_defaults["MAIL_PORT"]))
    MAIL_USE_TLS = _env_bool("MAIL_USE_TLS", default=_mail_defaults["MAIL_USE_TLS"])
    MAIL_USE_SSL = _env_bool("MAIL_USE_SSL", default=_mail_defaults["MAIL_USE_SSL"])
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.environ.get(
        "MAIL_DEFAULT_SENDER", os.environ.get("MAIL_USERNAME", "no-reply@example.com")
    )
    MAIL_SUPPRESS_SEND = _env_bool("MAIL_SUPPRESS_SEND", default=False)

    # Tokens
    INITIAL_PASSWORD_TOKEN_SALT = os.environ.get(
        "INITIAL_PASSWORD_TOKEN_SALT", "initial-password"
    )
    INITIAL_PASSWORD_TOKEN_MAX_AGE = int(
        os.environ.get("INITIAL_PASSWORD_TOKEN_MAX_AGE", 60 * 60 * 24 * 7)
    )