import json
from urllib.parse import urlparse
import sys
from pathlib import Path

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
    SECRET_KEY = "test-secret"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = False


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
def order_id(app):
    with app.app_context():
        plan = Plan(name="Test Plan", max_children=1, max_workshops_per_child=1, price_monthly=10000)
        db.session.add(plan)

        user = User(email="guardian@example.com", name="Guardian", password_hash="hash")
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
            external_id="fake-token",
        )
        db.session.add(order)
        db.session.commit()

        return order.id


@pytest.fixture
def guardian_credentials(app, order_id):
    credentials = {"email": "guardian@example.com", "password": "portal-secret"}

    with app.app_context():
        user = User.query.filter_by(email=credentials["email"]).first()
        user.set_password(credentials["password"])
        db.session.commit()

    return credentials


def test_webpay_failure_restores_context(client, app, order_id, monkeypatch):
    failure_response = {"status": "FAILED", "response_code": -1}
    monkeypatch.setattr(webpay_service, "commit_token", lambda token: failure_response)

    with app.app_context():
        order = Order.query.get(order_id)
        context = {
            "order_id": order.id,
            "guardian_email": "guardian@example.com",
            "plan_id": order.subscription.plan.id,
            "billing_cycle": order.subscription.billing_cycle.name,
            "temporary_password": "temp-pass",
        }
        token = order.external_id

    with client.session_transaction() as session_ctx:
        session_ctx["webpay_inscription"] = context

    response = client.post("/pago/webpay/retorno", data={"token_ws": token})
    assert response.status_code == 200

    with client.session_transaction() as session_ctx:
        assert session_ctx["webpay_inscription"] == context

    with app.app_context():
        refreshed_order = Order.query.get(order_id)
        assert refreshed_order.payment_status == PaymentStatus.failed
        assert json.loads(refreshed_order.detail) == context


def test_guardian_portal_rebuilds_webpay_context(client, app, order_id, guardian_credentials):
    login_response = client.post(
        "/auth/login",
        data=guardian_credentials,
        follow_redirects=False,
    )

    assert login_response.status_code == 302
    assert urlparse(login_response.headers["Location"]).path == "/portal/"

    retry_response = client.post(
        f"/portal/ordenes/{order_id}/webpay/reintentar",
        follow_redirects=False,
    )

    assert retry_response.status_code == 302
    assert urlparse(retry_response.headers["Location"]).path == f"/pago/{order_id}/webpay/iniciar"

    with client.session_transaction() as session_ctx:
        context = session_ctx.get("webpay_inscription")

    with app.app_context():
        order = Order.query.get(order_id)
        expected_context = {
            "order_id": order.id,
            "guardian_email": "guardian@example.com",
            "plan_id": order.subscription.plan_id,
            "billing_cycle": order.subscription.billing_cycle.name,
        }

    assert context == expected_context

    with app.app_context():
        refreshed_order = Order.query.get(order_id)
        assert json.loads(refreshed_order.detail) == expected_context