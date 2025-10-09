import sys
from datetime import time, datetime, timezone
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app import create_app
from app.extensions import db
from app.models import (
    DayOfWeek,
    Guardian,
    Order,
    PaymentMethod,
    Plan,
    Subscription,
    User,
    Workshop,
)


class TestConfig:
    TESTING = True
    SECRET_KEY = "test-secret"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = False
    MAIL_DEFAULT_SENDER = "test@example.com"
    MAIL_SUPPRESS_SEND = True
    INITIAL_PASSWORD_TOKEN_SALT = "test-salt"
    INITIAL_PASSWORD_TOKEN_MAX_AGE = 3600
    SERVER_NAME = "localhost"
    GOOGLE_CLIENT_ID = "test-client-id"
    GOOGLE_CLIENT_SECRET = "test-client-secret"


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


def _create_plan_and_workshop():
    plan = Plan(
        name="Plan Test",
        max_children=1,
        max_workshops_per_child=1,
        price_monthly=10000,
        quarterly_discount_pct=0,
    )
    workshop = Workshop(
        name="Taller Test",
        day_of_week=DayOfWeek.lunes,
        start_time=time(10, 0),
        end_time=time(11, 0),
        is_active=True,
    )
    db.session.add_all([plan, workshop])
    db.session.commit()
    return plan, workshop


def _login(client, user_id: int):
    with client.session_transaction() as session_ctx:
        session_ctx["_user_id"] = str(user_id)
        session_ctx["_fresh"] = True


def test_inscription_requires_google_login_redirects(client, app):
    with app.app_context():
        plan, _ = _create_plan_and_workshop()
        plan_id = plan.id

    response = client.get(f"/inscripcion/{plan_id}")

    assert response.status_code == 302
    assert response.headers["Location"].startswith("/auth/login")
    assert "show_google_help=1" in response.headers["Location"]


def test_inscription_creates_guardian_for_authenticated_user(client, app):
    with app.app_context():
        plan, workshop = _create_plan_and_workshop()
        user = User(email="guardian@example.com", name="Guardian", password_hash="hash")
        user.google_sub = "google-sub-123"
        user.activate()
        user.email_confirmed_at = datetime.now(timezone.utc)
        db.session.add(user)
        db.session.commit()

        plan_id = plan.id
        workshop_id = workshop.id
        user_id = user.id

    _login(client, user_id)

    response = client.post(
        f"/inscripcion/{plan_id}",
        data={
            "guardian_name": "Guardian",
            "guardian_email": "guardian@example.com",
            "phone": "+56912345678",
            "allow_whatsapp_group": "y",
            "children-0-name": "Niño Test",
            "children-0-birthdate": "2015-01-01",
            "children-0-knowledge_level": "none",
            "children-0-health_info": "",
            "children-0-allow_media": "y",
            "payment_method": "transfer",
            "workshops": [str(workshop_id)],
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "¡Inscripción confirmada!" in body
    assert "Inscripción creada correctamente" in body

    with app.app_context():
        user = db.session.get(User, user_id)
        guardian = user.guardian_profile
        assert guardian is not None
        assert guardian.phone == "+56912345678"
        subscription = Subscription.query.filter_by(guardian_id=guardian.id).first()
        assert subscription is not None
        order = Order.query.filter_by(subscription_id=subscription.id).first()
        assert order is not None
        assert order.payment_method == PaymentMethod.transfer
        assert user.password_reset_token_hash is None


def test_inscription_blocks_existing_guardian(client, app):
    with app.app_context():
        plan, _ = _create_plan_and_workshop()
        user = User(email="guardian2@example.com", name="Guardian", password_hash="hash")
        user.google_sub = "google-sub-456"
        user.activate()
        user.email_confirmed_at = datetime.now(timezone.utc)
        guardian = Guardian(user=user, phone="", allow_whatsapp_group=False)
        db.session.add_all([user, guardian])
        db.session.commit()

        plan_id = plan.id
        user_id = user.id

    _login(client, user_id)

    response = client.get(f"/inscripcion/{plan_id}")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Ya existe una inscripción asociada a tu cuenta" in body
