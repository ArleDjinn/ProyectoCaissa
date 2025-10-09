from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from flask_login import LoginManager
from flask_mail import Mail

try:  # pragma: no cover - dependencia opcional
    from authlib.integrations.flask_client import OAuth
except ModuleNotFoundError:  # pragma: no cover - fallback para entornos sin Authlib

    class _OAuthClientUnavailable:
        def __init__(self, name: str):
            self.name = name

        def authorize_redirect(self, *_, **__):
            raise RuntimeError("Authlib no está instalado. Instálalo para usar Google OAuth.")

        def authorize_access_token(self, *_, **__):
            raise RuntimeError("Authlib no está instalado. Instálalo para usar Google OAuth.")

        def parse_id_token(self, *_, **__):
            raise RuntimeError("Authlib no está instalado. Instálalo para usar Google OAuth.")

        def get(self, *_args, **_kwargs):
            raise RuntimeError("Authlib no está instalado. Instálalo para usar Google OAuth.")

    class OAuth:  # type: ignore[override]
        def __init__(self):
            self._clients: dict[str, _OAuthClientUnavailable] = {}

        def init_app(self, _app):
            return None

        def register(self, name: str, **_kwargs):
            self._clients[name] = _OAuthClientUnavailable(name)

        def create_client(self, name: str):
            return self._clients.get(name)

db = SQLAlchemy()
migrate = Migrate()
csrf = CSRFProtect()
login_manager = LoginManager()
login_manager.login_view = "auth.login"
mail = Mail()
oauth = OAuth()