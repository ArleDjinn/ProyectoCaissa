import json
from html.parser import HTMLParser
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
    SECRET_KEY = "test-secret"  # Solo para pruebas
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = False


class PortalCsrfConfig(TestConfig):
    WTF_CSRF_ENABLED = True


class HiddenInputParser(HTMLParser):
    """Parser simple para extraer inputs ocultos (ej. tokens CSRF)"""
    def __init__(self):
        super().__init__()
        self.values = {}

    def handle_starttag(self, tag, attrs):
        if tag != "input":
            return

        attributes = dict(attrs)
        name = attributes.get("name")
        if name:
            self.values[name] = attributes.get("value")


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


@pytest.fixture
def guardian_credentials(app, order_id):
    credentials = {"email": "guardian@example.com", "password": "portal-secret"}  # Solo para test

    with app.app_context():
        user = User.query.filter_by(email=credentials["email"]).first()
        user.set_password(credentials["password"])
        db.session.commit()

    return credentials


# ---------------------------
# Fixtures portal con CSRF
# ---------------------------

@pytest.fixture
def portal_app_with_csrf():
    app = create_app(PortalCsrfConfig)
    with app.app_context():
        db.create_all()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def portal_client(portal_app_with_csrf):
    return portal_app_with_csrf.test_client()


@pytest.fixture
def portal_order_id(portal_app_with_csrf):
    with portal_app_with_csrf.app_context():
        plan = Plan(
            name="Portal Plan",
            max_children=1,
            max_workshops_per_child=1,
            price_monthly=9000,
        )
        db.session.add(plan)

        user = User(email="portal-guardian@example.com", name="Portal Guardian", password_hash="hash")
        db.session.add(user)
        db.session.flush()

        guardian = Guardian(user=user, phone="555555", allow_whatsapp_group=False)
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
            amount_clp=9000,
            payment_method=PaymentMethod.webpay,
            payment_status=PaymentStatus.pending,
            detail=None,
            external_id="fake-token-portal",  # Ahora consistente
        )
        db.session.add(order)
        db.session.commit()

        return order.id


@pytest.fixture
def portal_guardian_credentials(portal_app_with_csrf, portal_order_id):
    credentials = {"email": "portal-guardian@example.com", "password": "portal-secret"}  # Solo test
    with portal_app_with_csrf.app_context():
        user = User.query.filter_by(email=credentials["email"]).first()
        user.set_password(credentials["password"])
        db.session.commit()
    return credentials


# ---------------------------
# Tests
# ---------------------------

def test_webpay_failure_restores_context(client, app, order_id, monkeypatch):
    failure_response = {"status": "FAILED", "response_code": -1}
    monkeypatch.setattr(webpay_service, "commit_token", lambda token: failure_response)

    with app.app_context():
        order = db.session.get(Order, order_id)
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
        refreshed_order = db.session.get(Order, order_id)
        assert refreshed_order.payment_status == PaymentStatus.failed
        assert json.loads(refreshed_order.detail) == context


def test_webpay_success_from_portal_keeps_existing_password(client, app, order_id, monkeypatch):
    success_response = {"status": "AUTHORIZED", "response_code": 0}
    monkeypatch.setattr(webpay_service, "commit_token", lambda token: success_response)

    with app.app_context():
        order = db.session.get(Order, order_id)
        user = order.subscription.guardian.user
        original_password_hash = user.password_hash
        context = {
            "order_id": order.id,
            "guardian_email": user.email,
            "plan_id": order.subscription.plan.id,
            "billing_cycle": order.subscription.billing_cycle.name,
        }
        token = order.external_id

    with client.session_transaction() as session_ctx:
        session_ctx["webpay_inscription"] = context

    response = client.post("/pago/webpay/retorno", data={"token_ws": token})
    assert response.status_code == 200
    assert b"Guarda esta contrase\xc3\xb1a temporal" not in response.data

    with app.app_context():
        refreshed_order = db.session.get(Order, order_id)
        assert refreshed_order.payment_status == PaymentStatus.paid
        assert refreshed_order.subscription.guardian.user.password_hash == original_password_hash
        assert refreshed_order.detail is None


def test_portal_webpay_retry_redirects_with_valid_csrf(
    portal_client, portal_app_with_csrf, portal_order_id, portal_guardian_credentials
):
    # Obtener token de CSRF del login
    login_page = portal_client.get("/auth/login")
    parser = HiddenInputParser()
    parser.feed(login_page.get_data(as_text=True))
    login_csrf = parser.values.get("csrf_token")

    assert login_csrf, "El formulario de login debe incluir el token CSRF"

    response = portal_client.post(
        "/auth/login",
        data={
            "email": portal_guardian_credentials["email"],
            "password": portal_guardian_credentials["password"],
            "csrf_token": login_csrf,
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    # Extraer CSRF del formulario de reintento
    dashboard = portal_client.get("/portal/")
    parser = HiddenInputParser()
    parser.feed(dashboard.get_data(as_text=True))
    form_csrf = parser.values.get("csrf_token")

    assert form_csrf, "El formulario de reintento debe incluir el token CSRF"

    retry_response = portal_client.post(
        f"/portal/ordenes/{portal_order_id}/webpay/reintentar",
        data={"csrf_token": form_csrf},
        follow_redirects=False,
    )

    assert retry_response.status_code == 302
    assert urlparse(retry_response.headers["Location"]).path == f"/pago/{portal_order_id}/webpay/iniciar"
