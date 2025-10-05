import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app import create_app
from app.extensions import db, mail
from app.models import User
from app.auth import generate_password_reset_token


class TestConfig:
    TESTING = True
    SECRET_KEY = "test-secret"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = False
    MAIL_SUPPRESS_SEND = True
    MAIL_DEFAULT_SENDER = "test@example.com"
    INITIAL_PASSWORD_TOKEN_SALT = "test-salt"
    INITIAL_PASSWORD_TOKEN_MAX_AGE = 3600
    SERVER_NAME = "example.com"


@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def create_admin_and_user():
    admin = User(email="admin@example.com", name="Admin", password_hash="")
    admin.set_password("AdminPass123!")
    admin.is_admin = True
    admin.activate()
    admin.email_confirmed_at = datetime.now(timezone.utc)

    guardian = User(email="guardian@example.com", name="Guardian", password_hash="")
    guardian.set_password("Guardian123!")
    guardian.activate()
    guardian.email_confirmed_at = datetime.now(timezone.utc)
    return admin, guardian


def test_admin_can_trigger_password_reset_email(client, app):
    with app.app_context():
        admin, guardian = create_admin_and_user()
        db.session.add_all([admin, guardian])
        db.session.commit()
        guardian_id = guardian.id

    login_response = client.post(
        "/auth/login",
        data={"email": "admin@example.com", "password": "AdminPass123!"},
        follow_redirects=True,
    )
    assert login_response.status_code == 200

    with mail.record_messages() as outbox:
        response = client.post(
            f"/admin/usuarios/{guardian_id}/reset-password",
            follow_redirects=True,
        )

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Se envió un enlace de restablecimiento" in body
    assert len(outbox) == 1
    message = outbox[0]
    assert "guardian@example.com" in message.recipients

    with app.app_context():
        refreshed = db.session.get(User, guardian_id)
        assert refreshed.password_reset_token_hash is not None


def test_user_can_complete_password_reset_flow(client, app):
    new_password = "NuevaClaveSegura1!"
    with app.app_context():
        user = User(email="reset@example.com", name="Reset", password_hash="")
        user.set_password("Temporal123!")
        user.activate()
        user.email_confirmed_at = datetime.now(timezone.utc)
        db.session.add(user)
        db.session.flush()
        token = generate_password_reset_token(user)
        user.set_password_reset_token(token)
        db.session.commit()
        user_id = user.id

    get_response = client.get(f"/auth/reset/{token}")
    assert get_response.status_code == 200
    assert "Crea una nueva contraseña" in get_response.get_data(as_text=True)

    post_response = client.post(
        f"/auth/reset/{token}",
        data={
            "password": new_password,
            "confirm_password": new_password,
        },
        follow_redirects=True,
    )
    assert post_response.status_code == 200
    assert "Tu contraseña fue actualizada correctamente" in post_response.get_data(as_text=True)

    with app.app_context():
        refreshed = db.session.get(User, user_id)
        assert refreshed.password_reset_token_hash is None
        assert refreshed.check_password(new_password)