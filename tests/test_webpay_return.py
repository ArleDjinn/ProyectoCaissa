import sys
from pathlib import Path

from datetime import datetime, timezone

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app import create_app
from app.extensions import db
from app.models import (
    BillingCycle,
    Guardian,
    Order,
    PaymentMethod,
    PaymentStatus,
    Plan,
    Subscription,
    User,
)
from app.services import webpay as webpay_service


class TestConfig:
    TESTING = True
    SECRET_KEY = "test-secret"  # Solo para pruebas
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = False
    MAIL_SUPPRESS_SEND = True
    MAIL_DEFAULT_SENDER = "test@example.com"
    INITIAL_PASSWORD_TOKEN_SALT = "test-salt"
    INITIAL_PASSWORD_TOKEN_MAX_AGE = 3600
    SERVER_NAME = "example.com"

# ---------------------------
# Fixtures base
# ---------------------------

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


@pytest.fixture
def order_id(app):
    with app.app_context():
        plan = Plan(
            name="Test Plan",
            max_children=1,
            max_workshops_per_child=1,
            price_monthly=10000,
        )
        db.session.add(plan)

        user = User(email="guardian@example.com", name="Guardian", password_hash="hash")
        user.activate()
        user.email_confirmed_at = datetime.now(timezone.utc)
        db.session.add(user)
        db.session.flush()

        guardian = Guardian(user=user, phone="123456789", allow_whatsapp_group=False)
        db.session.add(guardian)

        subscription = Subscription(
            guardian=guardian,
            plan=plan,
            billing_cycle=BillingCycle.monthly,
        )
        db.session.add(subscription)
        db.session.flush()

        order = Order(
            subscription=subscription,
            amount_clp=10000,
            payment_method=PaymentMethod.webpay,
            payment_status=PaymentStatus.pending,
            detail=None,
            external_id="fake-token",  # Consistencia: siempre usar un external_id
        )
        db.session.add(order)
        db.session.commit()

        return order.id

# ---------------------------
# Tests
# ---------------------------

def test_webpay_failure_marks_order_failed_without_retry(client, app, order_id, monkeypatch):
    failure_response = {"status": "FAILED", "response_code": -1}
    monkeypatch.setattr(webpay_service, "commit_token", lambda token: failure_response)

    with app.app_context():
        order = db.session.get(Order, order_id)
        token = order.external_id

    with client.session_transaction() as session_ctx:
        session_ctx["webpay_inscription"] = {"order_id": order.id}

    response = client.post("/pago/webpay/retorno", data={"token_ws": token})
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Elige un método alternativo" in body

    with client.session_transaction() as session_ctx:
        assert "webpay_inscription" not in session_ctx

    with app.app_context():
        refreshed_order = db.session.get(Order, order_id)
        assert refreshed_order.payment_status == PaymentStatus.failed
        assert refreshed_order.detail is None

def test_webpay_success_from_portal_keeps_existing_password(client, app, order_id, monkeypatch):
    success_response = {"status": "AUTHORIZED", "response_code": 0}
    monkeypatch.setattr(webpay_service, "commit_token", lambda token: success_response)

    with app.app_context():
        order = db.session.get(Order, order_id)
        user = order.subscription.guardian.user
        original_password_hash = user.password_hash
        token = order.external_id

    with client.session_transaction() as session_ctx:
        session_ctx["webpay_inscription"] = {"order_id": order.id}

    response = client.post("/pago/webpay/retorno", data={"token_ws": token})
    assert response.status_code == 200
    body = response.get_data(as_text=True)

    assert "Guarda esta contraseña temporal" not in body

    with app.app_context():
        refreshed_order = db.session.get(Order, order_id)
        assert refreshed_order.payment_status == PaymentStatus.paid
        assert refreshed_order.subscription.guardian.user.password_hash == original_password_hash
        assert refreshed_order.detail is None
