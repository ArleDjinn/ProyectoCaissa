from pathlib import Path
import sys
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
def order_context(app):
    with app.app_context():
        plan = Plan(
            name="Test Plan",
            max_children=1,
            max_workshops_per_child=1,
            price_monthly=10000,
        )
        db.session.add(plan)

        owner_user = User(email="owner@example.com", name="Owner", password_hash="")
        owner_user.set_password("owner-secret")
        owner_user.activate()
        owner_user.email_confirmed_at = datetime.now(timezone.utc)
        db.session.add(owner_user)
        db.session.flush()

        guardian_owner = Guardian(user=owner_user, phone="123456789", allow_whatsapp_group=False)
        db.session.add(guardian_owner)

        subscription = Subscription(
            guardian=guardian_owner,
            plan=plan,
            billing_cycle=BillingCycle.monthly,
        )
        db.session.add(subscription)
        db.session.flush()

        order = Order(
            subscription=subscription,
            amount_clp=10000,
            payment_method=PaymentMethod.transfer,
            payment_status=PaymentStatus.pending,
        )
        db.session.add(order)

        other_user = User(email="intruder@example.com", name="Intruder", password_hash="")
        other_user.set_password("intruder-secret")
        other_user.activate()
        other_user.email_confirmed_at = datetime.now(timezone.utc)
        db.session.add(other_user)
        db.session.flush()

        other_guardian = Guardian(user=other_user, phone="987654321", allow_whatsapp_group=False)
        db.session.add(other_guardian)

        admin_user = User(email="admin@example.com", name="Admin", password_hash="", is_admin=True)
        admin_user.set_password("admin-secret")
        admin_user.activate()
        admin_user.email_confirmed_at = datetime.now(timezone.utc)
        db.session.add(admin_user)

        outsider_user = User(email="outsider@example.com", name="Outsider", password_hash="")
        outsider_user.set_password("outsider-secret")
        db.session.add(outsider_user)

        db.session.commit()

        return {
            "order_id": order.id,
            "owner": {"email": owner_user.email, "password": "owner-secret"},
            "intruder": {"email": other_user.email, "password": "intruder-secret"},
            "admin": {"email": admin_user.email, "password": "admin-secret"},
            "outsider": {"email": outsider_user.email, "password": "outsider-secret"},
            "outsider_id": outsider_user.id,
        }


def login(client, credentials):
    return client.post("/auth/login", data=credentials, follow_redirects=True)


def test_order_owner_can_access_detail(client, order_context):
    login(client, order_context["owner"])

    response = client.get(f"/pago/{order_context['order_id']}")
    assert response.status_code == 200
    assert f"Orden #{order_context['order_id']}".encode() in response.data


def test_other_guardian_gets_403(client, order_context):
    login(client, order_context["intruder"])

    response = client.get(f"/pago/{order_context['order_id']}")
    assert response.status_code == 403


def test_admin_can_access_any_order(client, order_context):
    login(client, order_context["admin"])

    response = client.get(f"/pago/{order_context['order_id']}")
    assert response.status_code == 200


def test_user_without_guardian_profile_gets_404(client, order_context):
    with client.session_transaction() as session_ctx:
        session_ctx["_user_id"] = str(order_context["outsider_id"])
        session_ctx["_fresh"] = True

    response = client.get(f"/pago/{order_context['order_id']}")
    assert response.status_code == 404