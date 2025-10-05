from datetime import date, datetime, time, timezone
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
    Child,
    Plan,
    Workshop,
    Subscription,
    Enrollment,
    DayOfWeek,
    BillingCycle,
    SubscriptionStatus,
    EnrollmentStatus,
    KnowledgeLevel,
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
def admin_data(app):
    with app.app_context():
        admin = User(email="admin@example.com", name="Admin", password_hash="", is_admin=True)
        admin.set_password("secret")
        admin.activate()
        admin.email_confirmed_at = datetime.now(timezone.utc)
        db.session.add(admin)

        guardian_user = User(email="guardian@example.com", name="Guardian Uno", password_hash="")
        guardian_user.set_password("guardian")
        guardian_user.activate()
        guardian_user.email_confirmed_at = datetime.now(timezone.utc)
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

        workshop_one = Workshop(
            name="Taller A",
            day_of_week=DayOfWeek.lunes,
            start_time=time(16, 0),
            end_time=time(17, 30),
            is_active=True,
        )
        workshop_two = Workshop(
            name="Taller B",
            day_of_week=DayOfWeek.miercoles,
            start_time=time(18, 0),
            end_time=time(19, 30),
            is_active=True,
        )
        db.session.add_all([workshop_one, workshop_two])

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
            birthdate=date(2014, 5, 20),
            knowledge_level=KnowledgeLevel.basic,
            allow_media=True,
        )
        db.session.add(child)
        db.session.flush()

        enrollment = Enrollment(
            subscription=subscription,
            child=child,
            workshop=workshop_one,
            status=EnrollmentStatus.active,
        )
        db.session.add(enrollment)
        db.session.commit()

        return {
            "admin_credentials": {"email": admin.email, "password": "secret"},
            "subscription_id": subscription.id,
            "guardian_id": guardian.id,
            "child_id": child.id,
            "workshop_ids": (workshop_one.id, workshop_two.id),
        }


def login(client, credentials):
    return client.post("/auth/login", data=credentials, follow_redirects=True)


def test_full_subscription_flow(client, app, admin_data):
    login_response = login(client, admin_data["admin_credentials"])
    assert login_response.status_code == 200

    list_response = client.get("/admin/dashboard/subscriptions")
    assert list_response.status_code == 200
    assert b"Plan Familiar" in list_response.data

    detail_url = f"/admin/dashboard/subscriptions/{admin_data['subscription_id']}"
    detail_response = client.get(detail_url)
    assert detail_response.status_code == 200
    assert b"Ni\xc3\xb1a Uno" in detail_response.data

    update_guardian_resp = client.post(
        detail_url,
        data={
            "action": "update_guardian",
            "guardian-name": "Guardian Actualizado",
            "guardian-email": "nuevo@example.com",
            "guardian-phone": "+56922222222",
            "guardian-allow_whatsapp_group": "y",
        },
        follow_redirects=True,
    )
    assert b"Datos de contacto actualizados" in update_guardian_resp.data

    with app.app_context():
        guardian = db.session.get(Guardian, admin_data["guardian_id"])
        assert guardian.user.name == "Guardian Actualizado"
        assert guardian.user.email == "nuevo@example.com"
        assert guardian.phone == "+56922222222"
        assert guardian.allow_whatsapp_group is True

    add_child_resp = client.post(
        detail_url,
        data={
            "action": "add_child",
            "new_child-name": "Ni\xc3\xb1o Nuevo",
            "new_child-birthdate": "2016-02-02",
            "new_child-knowledge_level": "basic",
            "new_child-health_info": "Sin alergias",
            "new_child-allow_media": "y",
        },
        follow_redirects=True,
    )
    assert b"Ni\xc3\xb1o/a agregado" in add_child_resp.data

    with app.app_context():
        guardian = db.session.get(Guardian, admin_data["guardian_id"])
        new_child = next(child for child in guardian.children if child.name == "Ni\xc3\xb1o Nuevo")
        new_child_id = new_child.id

    update_child_resp = client.post(
        detail_url,
        data={
            "action": "update_child",
            f"child-{new_child_id}-child_id": str(new_child_id),
            f"child-{new_child_id}-name": "Ni\xc3\xb1o Actualizado",
            f"child-{new_child_id}-birthdate": "2016-02-02",
            f"child-{new_child_id}-knowledge_level": "regular",
            f"child-{new_child_id}-health_info": "Observaciones",
        },
        follow_redirects=True,
    )
    assert b"Datos del ni\xc3\xb1o/a actualizados" in update_child_resp.data

    with app.app_context():
        updated_child = db.session.get(Child, new_child_id)
        assert updated_child.name == "Ni\xc3\xb1o Actualizado"
        assert updated_child.knowledge_level == KnowledgeLevel.regular

    delete_child_resp = client.post(
        detail_url,
        data={
            "action": "delete_child",
            f"delete-child-{new_child_id}-child_id": str(new_child_id),
        },
        follow_redirects=True,
    )
    assert b"Ni\xc3\xb1o/a eliminado" in delete_child_resp.data

    with app.app_context():
        assert db.session.get(Child, new_child_id) is None

    enrollment_id = None
    with app.app_context():
        enrollment = (
            db.session.query(Enrollment)
            .filter_by(subscription_id=admin_data["subscription_id"], status=EnrollmentStatus.active)
            .first()
        )
        enrollment_id = enrollment.id

    workshop_one_id, workshop_two_id = admin_data["workshop_ids"]
    move_enrollment_resp = client.post(
        detail_url,
        data={
            "action": "move_enrollment",
            f"move-{enrollment_id}-enrollment_id": str(enrollment_id),
            f"move-{enrollment_id}-new_workshop_id": str(workshop_two_id),
        },
        follow_redirects=True,
    )
    assert b"Matr\xc3\xadcula movida" in move_enrollment_resp.data

    with app.app_context():
        subscription = db.session.get(Subscription, admin_data["subscription_id"])
        active_enrollments = [e for e in subscription.enrollments if e.status == EnrollmentStatus.active]
        assert len(active_enrollments) == 1
        new_enrollment = active_enrollments[0]
        assert new_enrollment.workshop_id == workshop_two_id

    cancel_enrollment_resp = client.post(
        detail_url,
        data={
            "action": "cancel_enrollment",
            f"cancel-{new_enrollment.id}-enrollment_id": str(new_enrollment.id),
        },
        follow_redirects=True,
    )
    assert b"Matr\xc3\xadcula cancelada" in cancel_enrollment_resp.data

    with app.app_context():
        canceled_enrollment = db.session.get(Enrollment, new_enrollment.id)
        assert canceled_enrollment.status == EnrollmentStatus.canceled

    cancel_subscription_resp = client.post(
        detail_url,
        data={"action": "cancel_subscription"},
        follow_redirects=True,
    )
    assert b"Suscripci\xc3\xb3n cancelada" in cancel_subscription_resp.data

    with app.app_context():
        subscription = db.session.get(Subscription, admin_data["subscription_id"])
        assert subscription.status == SubscriptionStatus.canceled
        assert subscription.end_date is not None
        for enrollment in subscription.enrollments:
            assert enrollment.status != EnrollmentStatus.active

    reactivate_resp = client.post(
        detail_url,
        data={"action": "activate_subscription"},
        follow_redirects=True,
    )
    assert b"Suscripci\xc3\xb3n activada" in reactivate_resp.data

    with app.app_context():
        subscription = db.session.get(Subscription, admin_data["subscription_id"])
        assert subscription.status == SubscriptionStatus.active
        assert subscription.end_date is None
