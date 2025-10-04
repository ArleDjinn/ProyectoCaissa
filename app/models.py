# app/models.py
import enum
from datetime import datetime, date, timezone
from .extensions import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash


# ---------- Mixins ----------
class UtcTimestampMixin:
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

# ---------- Enums ----------
class DayOfWeek(enum.Enum):
    lunes = "Lunes"
    martes = "Martes"
    miercoles = "Miércoles"
    jueves = "Jueves"
    viernes = "Viernes"
    sabado = "Sábado"
    domingo = "Domingo"

class KnowledgeLevel(enum.Enum):
    none = "Sin experiencia"
    basic = "Básico"
    regular = "Juega regularmente"

class BillingCycle(enum.Enum):
    monthly = "Mensual"
    quarterly = "Trimestral"

class SubscriptionStatus(enum.Enum):
    pending = "Pendiente"
    active = "Activa"
    suspended = "Suspendida"
    canceled = "Cancelada"

class EnrollmentStatus(enum.Enum):
    active = "Activa"
    changed = "Cambiada"
    canceled = "Cancelada"

class PaymentMethod(enum.Enum):
    webpay = "Webpay"
    transfer = "Transferencia"
    in_person = "Presencial"

class PaymentStatus(enum.Enum):
    pending = "Pendiente"
    reserved = "Reservada"
    paid = "Pagada"
    failed = "Fallida"


# ---------- Core ----------
class User(UserMixin, UtcTimestampMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    password_hash = db.Column(db.String(512), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    last_login_at = db.Column(db.DateTime(timezone=True), nullable=True)
    previous_login_at = db.Column(db.DateTime(timezone=True), nullable=True)

    guardian_profile = db.relationship(
        "Guardian",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<User {self.email} admin={self.is_admin}>"


class Guardian(UtcTimestampMixin, db.Model):
    __tablename__ = "guardians"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"),
        unique=True, nullable=False
    )
    phone = db.Column(db.String(20), nullable=False)
    allow_whatsapp_group = db.Column(db.Boolean, default=False, nullable=False)

    user = db.relationship("User", back_populates="guardian_profile")
    children = db.relationship("Child", back_populates="guardian",
                               cascade="all, delete-orphan")
    subscriptions = db.relationship("Subscription", back_populates="guardian",
                                    cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Guardian user={self.user_id}>"


class Child(UtcTimestampMixin, db.Model):
    __tablename__ = "children"

    id = db.Column(db.Integer, primary_key=True)
    guardian_id = db.Column(
        db.Integer, db.ForeignKey("guardians.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    name = db.Column(db.String(120), nullable=False)
    birthdate = db.Column(db.Date, nullable=True)
    knowledge_level = db.Column(db.Enum(KnowledgeLevel), nullable=True)
    health_info = db.Column(db.Text, nullable=True)
    allow_media = db.Column(db.Boolean, default=False, nullable=False)

    guardian = db.relationship("Guardian", back_populates="children")
    enrollments = db.relationship("Enrollment", back_populates="child",
                                  cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Child {self.name} guardian={self.guardian_id}>"


# ---------- Oferta ----------
class Plan(UtcTimestampMixin, db.Model):
    __tablename__ = "plans"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    max_children = db.Column(db.Integer, nullable=False)
    max_workshops_per_child = db.Column(db.Integer, nullable=False)
    price_monthly = db.Column(db.Integer, nullable=False)
    quarterly_discount_pct = db.Column(db.Integer, default=15, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    subscriptions = db.relationship("Subscription", back_populates="plan")

    def __repr__(self):
        return f"<Plan {self.name}>"


class Workshop(UtcTimestampMixin, db.Model):
    __tablename__ = "workshops"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    day_of_week = db.Column(db.Enum(DayOfWeek), nullable=False, index=True)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=True)
    address = db.Column(db.String(200), nullable=True)
    capacity = db.Column(db.Integer, nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    enrollments = db.relationship("Enrollment", back_populates="workshop")

    def __repr__(self):
        return f"<Workshop {self.name} {self.day_of_week.value} {self.start_time}>"


# ---------- Suscripciones / Inscripciones / Pagos ----------
class Subscription(UtcTimestampMixin, db.Model):
    __tablename__ = "subscriptions"

    id = db.Column(db.Integer, primary_key=True)
    guardian_id = db.Column(
        db.Integer, db.ForeignKey("guardians.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    plan_id = db.Column(db.Integer, db.ForeignKey("plans.id"), nullable=False)
    reglamento_accepted_at = db.Column(db.DateTime(timezone=True), nullable=True)

    billing_cycle = db.Column(db.Enum(BillingCycle), nullable=False)
    status = db.Column(db.Enum(SubscriptionStatus),
                       default=SubscriptionStatus.pending, nullable=False)
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)

    guardian = db.relationship("Guardian", back_populates="subscriptions")
    plan = db.relationship("Plan", back_populates="subscriptions")
    orders = db.relationship("Order", back_populates="subscription",
                             cascade="all, delete-orphan")
    enrollments = db.relationship("Enrollment", back_populates="subscription",
                                  cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Subscription {self.id} guardian={self.guardian_id} plan={self.plan_id}>"


class Enrollment(UtcTimestampMixin, db.Model):
    __tablename__ = "enrollments"

    id = db.Column(db.Integer, primary_key=True)
    subscription_id = db.Column(
        db.Integer, db.ForeignKey("subscriptions.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    child_id = db.Column(
        db.Integer, db.ForeignKey("children.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    workshop_id = db.Column(db.Integer, db.ForeignKey("workshops.id"),
                            nullable=False, index=True)

    status = db.Column(db.Enum(EnrollmentStatus),
                       default=EnrollmentStatus.active, nullable=False)
    notes = db.Column(db.Text, nullable=True)

    subscription = db.relationship("Subscription", back_populates="enrollments")
    child = db.relationship("Child", back_populates="enrollments")
    workshop = db.relationship("Workshop", back_populates="enrollments")

    def __repr__(self):
        return f"<Enrollment child={self.child_id} workshop={self.workshop_id}>"


class Order(UtcTimestampMixin, db.Model):
    __tablename__ = "orders"

    id = db.Column(db.Integer, primary_key=True)
    subscription_id = db.Column(
        db.Integer, db.ForeignKey("subscriptions.id", ondelete="CASCADE"),
        nullable=False, index=True
    )

    amount_clp = db.Column(db.Integer, nullable=False)
    payment_method = db.Column(db.Enum(PaymentMethod), nullable=False)
    payment_status = db.Column(
        db.Enum(PaymentStatus), default=PaymentStatus.pending, nullable=False
    )
    currency = db.Column(db.String(3), default="CLP", nullable=False)

    detail = db.Column(db.Text, nullable=True)       # snapshot JSON si quieres
    external_id = db.Column(db.String(120), nullable=True)  # id de Webpay, etc.

    subscription = db.relationship("Subscription", back_populates="orders")

    def __repr__(self):
        return f"<Order {self.id} sub={self.subscription_id} {self.amount_clp} {self.payment_status.name}>"