from pathlib import Path
import sys
from datetime import datetime, timezone

import pytest
from flask import session
from flask_login import login_user


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app import create_app
from app.extensions import db
from app.models import Guardian, Child, User


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

@pytest.fixture
def app():
    app = create_app(TestConfig)

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def admin_setup(app):
    with app.app_context():
        admin = User(
            email="admin-dashboard@example.com",
            name="Admin Dashboard",
            password_hash="",
            is_admin=True,
        )
        admin.set_password("admin-secret")
        admin.activate()
        admin.email_confirmed_at = datetime.now(timezone.utc)
        db.session.add(admin)

        guardian_user = User(
            email="guardian@example.com",
            name="Guardian",
            password_hash="",
        )
        guardian_user.set_password("guardian-secret")
        guardian_user.activate()
        guardian_user.email_confirmed_at = datetime.now(timezone.utc)
        db.session.add(guardian_user)
        db.session.flush()

        guardian = Guardian(
            user=guardian_user,
            phone="123456789",
            allow_whatsapp_group=False,
        )
        db.session.add(guardian)
        db.session.flush()

        existing_child = Child(name="Niño Existente", guardian=guardian)
        db.session.add(existing_child)
        db.session.commit()

        return {
            "admin_id": admin.id,
            "guardian_id": guardian.id,
            "existing_child_name": existing_child.name,
        }


def force_login(client, app, user_id: int):
    with app.app_context():
        user = db.session.get(User, user_id)
        user.previous_login_at = user.last_login_at
        user.last_login_at = datetime.now(timezone.utc)
        db.session.commit()

    with app.test_request_context("/"):
        user = db.session.get(User, user_id)
        login_user(user, force=True)
        session_data = dict(session)

    with client.session_transaction() as session_ctx:
        session_ctx.clear()
        session_ctx.update(session_data)


def test_admin_dashboard_lists_children_created_between_logins(client, app, admin_setup):
    admin_id = admin_setup["admin_id"]

    force_login(client, app, admin_id)

    logout_response = client.get("/auth/logout", follow_redirects=True)
    assert logout_response.status_code == 200

    with app.app_context():
        guardian = db.session.get(Guardian, admin_setup["guardian_id"])
        new_child = Child(name="Niño Nuevo", guardian=guardian)
        db.session.add(new_child)
        db.session.commit()
        new_child_name = new_child.name

    force_login(client, app, admin_id)

    dashboard_response = client.get("/admin/dashboard/pagos")
    assert dashboard_response.status_code == 200
    assert b"Se han inscrito <strong>1</strong>" in dashboard_response.data
    assert new_child_name.encode() in dashboard_response.data
    assert admin_setup["existing_child_name"].encode() not in dashboard_response.data