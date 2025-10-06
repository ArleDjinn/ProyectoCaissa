from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sys

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app import create_app
from app.extensions import db
from app.models import (
    User,
    Guardian,
    Plan,
    Subscription,
    PaymentStatus,
    PaymentMethod,
    SubscriptionStatus,
    BillingCycle,
    Order,
)


class TestConfig:
    TESTING = True
    SECRET_KEY = "test-secret"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = False
    MAIL_SUPPRESS_SEND = True
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
        now = datetime.now(timezone.utc)

        admin = User(email="admin@example.com", name="Admin", password_hash="", is_admin=True)
        admin.set_password("secret")
        admin.activate()
        admin.email_confirmed_at = now
        db.session.add(admin)

        guardian_user = User(email="guardian@example.com", name="Guardian Uno", password_hash="")
        guardian_user.set_password("guardian")
        guardian_user.activate()
        guardian_user.email_confirmed_at = now
        db.session.add(guardian_user)
        db.session.flush()

        guardian = Guardian(user=guardian_user, phone="+56911111111", allow_whatsapp_group=False)
        db.session.add(guardian)

        plan = Plan(
            name="Plan Familiar",
            max_children=2,
            max_workshops_per_child=2,
            price_monthly=25000,
            quarterly_discount_pct=10,
            is_active=True,
        )
        db.session.add(plan)
        db.session.flush()

        subscription = Subscription(
            guardian=guardian,
            plan=plan,
            billing_cycle=BillingCycle.monthly,
            status=SubscriptionStatus.active,
            start_date=date(2024, 1, 1),
        )
        db.session.add(subscription)
        db.session.flush()

        last_order = Order(
            subscription=subscription,
            amount_clp=plan.price_monthly,
            payment_method=PaymentMethod.transfer,
            payment_status=PaymentStatus.paid,
        )
        last_order.created_at = now - timedelta(days=40)
        db.session.add(last_order)
        db.session.commit()

        return {
            "admin_credentials": {"email": admin.email, "password": "secret"},
            "subscription_id": subscription.id,
            "expected_amount": plan.price_monthly,
        }


def login(client, credentials):
    return client.post("/auth/login", data=credentials, follow_redirects=True)


def test_dashboard_lists_subscriptions_due(client, admin_setup):
    response = login(client, admin_setup["admin_credentials"])
    assert response.status_code == 200

    dashboard_response = client.get("/admin/dashboard/pagos")
    assert dashboard_response.status_code == 200
    assert b"Renovaci\xc3\xb3n de \xc3\xb3rdenes de pago" in dashboard_response.data
    assert b"Emitir orden" in dashboard_response.data
    assert b"guardian@example.com" in dashboard_response.data


def test_issue_subscription_order_creates_new_pending_order(client, app, admin_setup):
    login_response = login(client, admin_setup["admin_credentials"])
    assert login_response.status_code == 200

    subscription_id = admin_setup["subscription_id"]

    issue_response = client.post(
        f"/admin/dashboard/pagos/subscriptions/{subscription_id}/emitir",
        follow_redirects=True,
    )
    assert issue_response.status_code == 200

    with app.app_context():
        orders = (
            Order.query.filter_by(subscription_id=subscription_id)
            .order_by(Order.created_at.desc())
            .all()
        )
        assert len(orders) == 2
        new_order = orders[0]
        assert new_order.payment_status == PaymentStatus.pending
        assert new_order.payment_method == PaymentMethod.transfer
        assert new_order.amount_clp == admin_setup["expected_amount"]
