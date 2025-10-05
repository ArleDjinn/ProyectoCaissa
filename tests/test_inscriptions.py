import sys
from datetime import time
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app import create_app
from app.extensions import db
from app.models import (
    Plan,
    Workshop,
    DayOfWeek,
    User,
    Subscription,
)


class TestConfig:
    TESTING = True
    SECRET_KEY = "test-secret"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = False
    MAIL_DEFAULT_SENDER = "test@example.com"
    MAIL_SUPPRESS_SEND = False
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


def test_inscription_shows_warning_when_email_fails(monkeypatch, client, app):
    with app.app_context():
        plan, workshop = _create_plan_and_workshop()
        plan_id = plan.id
        workshop_id = workshop.id

    def fail_send(_msg):
        raise RuntimeError("Mail server unavailable")

    monkeypatch.setattr("app.inscriptions.mail.send", fail_send)

    response = client.post(
        f"/inscripcion/{plan_id}",
        data={
            "guardian_name": "Nombre Tutor",
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
    assert "No pudimos enviar el correo de confirmación" in body
    assert "Inscripción creada correctamente" in body

    with app.app_context():
        user = User.query.filter_by(email="guardian@example.com").first()
        assert user is not None
        assert user.password_reset_token_hash is not None
        guardian = user.guardian_profile
        assert guardian is not None
        subscription = Subscription.query.filter_by(guardian_id=guardian.id).first()
        assert subscription is not None
        assert subscription.created_at is not None