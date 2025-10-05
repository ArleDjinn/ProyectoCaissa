import sys
from datetime import date, time
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app import create_app
from app.extensions import db
from app.models import (
    BillingCycle,
    Child,
    DayOfWeek,
    Enrollment,
    EnrollmentStatus,
    Guardian,
    KnowledgeLevel,
    Plan,
    Subscription,
    SubscriptionStatus,
    User,
    Workshop,
)
from app.services import subscriptions as subscription_service


class TestConfig:
    TESTING = True
    SECRET_KEY = "test-secret"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = False
    MAIL_SUPPRESS_SEND = True


@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


def test_cancel_subscription_cancels_active_enrollments_and_sets_end_date(app):
    with app.app_context():
        user = User(email="guardian@example.com", name="Guardian", password_hash="")
        user.set_password("secret")
        user.activate()
        db.session.add(user)

        guardian = Guardian(user=user, phone="+56900000000", allow_whatsapp_group=False)
        db.session.add(guardian)

        plan = Plan(
            name="Plan Test",
            max_children=2,
            max_workshops_per_child=2,
            price_monthly=20000,
            quarterly_discount_pct=0,
            is_active=True,
        )
        db.session.add(plan)

        workshop = Workshop(
            name="Taller Test",
            day_of_week=DayOfWeek.lunes,
            start_time=time(10, 0),
            end_time=time(11, 0),
            is_active=True,
        )
        db.session.add(workshop)

        subscription = Subscription(
            guardian=guardian,
            plan=plan,
            billing_cycle=BillingCycle.monthly,
            status=SubscriptionStatus.active,
            start_date=date(2024, 1, 1),
        )
        db.session.add(subscription)

        child = Child(
            guardian=guardian,
            name="Niña Uno",
            birthdate=date(2015, 6, 1),
            knowledge_level=KnowledgeLevel.basic,
            allow_media=True,
        )
        db.session.add(child)

        active_enrollment = Enrollment(
            subscription=subscription,
            child=child,
            workshop=workshop,
            status=EnrollmentStatus.active,
        )
        already_canceled = Enrollment(
            subscription=subscription,
            child=child,
            workshop=workshop,
            status=EnrollmentStatus.canceled,
        )
        db.session.add_all([active_enrollment, already_canceled])
        db.session.flush()

        subscription_service.cancel_subscription(subscription)
        db.session.flush()

        assert subscription.status == SubscriptionStatus.canceled
        assert subscription.end_date == date.today()
        assert all(enrollment.status == EnrollmentStatus.canceled for enrollment in subscription.enrollments)
