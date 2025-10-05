import math
import secrets
from datetime import datetime, timezone
from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from .forms import InscriptionForm, ChildForm
from .models import User, Plan, Workshop, BillingCycle, PaymentMethod, KnowledgeLevel, Subscription
from .extensions import db, mail
from .services import guardians as guardian_service
from .services import subscriptions as subscription_service
from .services import enrollments as enrollment_service
from .services import orders as order_service
from sqlalchemy.exc import SQLAlchemyError
from itsdangerous import URLSafeTimedSerializer
from flask_mail import Message

bp = Blueprint("inscriptions", __name__, template_folder="templates")

def _get_serializer() -> URLSafeTimedSerializer:
    secret_key = current_app.config["SECRET_KEY"]
    salt = current_app.config["INITIAL_PASSWORD_TOKEN_SALT"]
    return URLSafeTimedSerializer(secret_key, salt=salt)

def _generate_initial_password_token(user: User) -> str:
    serializer = _get_serializer()
    return serializer.dumps({"user_id": user.id, "purpose": "initial-password"})

def send_initial_password_email(user: User, token: str, plan: Plan):
    confirm_url = url_for("auth.confirm_initial_password", token=token, _external=True)
    max_age = current_app.config["INITIAL_PASSWORD_TOKEN_MAX_AGE"]
    expiration_hours = max(1, math.ceil(max_age / 3600))
    msg = Message(
        subject="Confirma tu acceso a Proyecto Caissa",
        recipients=[user.email],
    )
    msg.body = render_template(
        "emails/initial_password.txt",
        user=user,
        plan=plan,
        confirm_url=confirm_url,
        expiration_hours=expiration_hours,
    )
    msg.html = render_template(
        "emails/initial_password.html",
        user=user,
        plan=plan,
        confirm_url=confirm_url,
        expiration_hours=expiration_hours,
    )
    try:
        mail.send(msg)
    except Exception as exc:
        current_app.logger.error(
            "Error enviando correo de contraseña inicial a %s: %s",
            user.email,
            exc,
            exc_info=True,
        )
        flash(
            "No pudimos enviar el correo de confirmación en este momento. "
            "Te contactaremos manualmente o inténtalo nuevamente más tarde.",
            "warning",
        )

@bp.route("/inscripcion/<int:plan_id>", methods=["GET", "POST"])
def inscripcion(plan_id):

    plan = Plan.query.get_or_404(plan_id)
    form = InscriptionForm()

    # Ajustar cantidad de subformularios de niños según el plan
    while len(form.children) < plan.max_children:
        form.children.append_entry()

    # talleres activos
    workshop_choices = [
        (w.id, f"{w.name} ({w.day_of_week.value} {w.start_time.strftime('%H:%M')})")
        for w in Workshop.query.filter_by(is_active=True).all()
    ]
    form.workshops.choices = workshop_choices

    # lee billing (?billing=quarterly)
    billing_param = (request.args.get("billing") or "").lower()
    billing_cycle = BillingCycle.quarterly if billing_param == "quarterly" else BillingCycle.monthly

    if form.validate_on_submit():
        # Validar si ya existe un usuario con ese correo
        existing_user = User.query.filter_by(email=form.guardian_email.data).first()
        if existing_user:
            flash(
                "⚠️ Ya existe una inscripción con este correo. Contáctanos si deseas agregar otro hijo o cambiar tu plan.",
                "warning",
            )
            return render_template("inscripcion.html", form=form, plan=plan, billing_cycle=billing_cycle)

        try:
            # Crear User inactivo hasta confirmar
            placeholder_password = secrets.token_urlsafe(32)

            user = User(name=form.guardian_name.data, email=form.guardian_email.data)
            user.set_password(placeholder_password)
            user.deactivate()
            db.session.add(user)
            db.session.flush()

            token = _generate_initial_password_token(user)
            user.set_password_reset_token(token)

            # Guardian
            guardian = guardian_service.create_guardian(
                user=user,
                phone=form.phone.data,
                allow_whatsapp_group=form.allow_whatsapp_group.data,
            )

            # Subscription (estado = pending)
            subscription = subscription_service.create_subscription(
                guardian=guardian,
                plan=plan,
                billing_cycle=billing_cycle,
            )

            # Children dinámicos
            children_objs = []
            for child_form in form.children.entries:
                if child_form.form.name.data:
                    child = guardian_service.create_child(
                        guardian=guardian,
                        name=child_form.form.name.data,
                        birthdate=child_form.form.birthdate.data,
                        knowledge_level=KnowledgeLevel[child_form.form.knowledge_level.data]
                        if child_form.form.knowledge_level.data else None,
                        health_info=child_form.form.health_info.data,
                        allow_media=child_form.form.allow_media.data,
                    )
                    children_objs.append(child)

            # Enrollments: aplicar talleres a cada hijo creado
            selected_workshops = form.workshops.data
            for child in children_objs:
                for wid in selected_workshops:
                    workshop = Workshop.query.get(wid)
                    enrollment_service.create_enrollment(subscription, child, workshop)

            # Crear Order
            method = PaymentMethod[form.payment_method.data]
            amount = (
                plan.price_monthly
                if billing_cycle == BillingCycle.monthly
                else int(plan.price_monthly * 3 * (1 - plan.quarterly_discount_pct / 100))
            )

            order = order_service.create_order(subscription, amount, method)
            subscription.reglamento_accepted_at = datetime.now(timezone.utc)

            db.session.commit()  # ✅ commit antes de redirigir

            send_initial_password_email(user, token, plan)

            if method == PaymentMethod.webpay:
                session["webpay_inscription"] = {
                    "order_id": order.id,
                    "temporary_password": placeholder_password,
                    "guardian_email": form.guardian_email.data,
                    "plan_id": plan.id,
                    "billing_cycle": billing_cycle.name,
                }
                return redirect(url_for("orders.start_webpay", order_id=order.id))

            flash(
                "✅ Inscripción creada correctamente. Revisa tu correo para confirmar la cuenta y definir tu contraseña.",
                "success",
            )

            return render_template(
                "inscripcion_confirmacion.html",
                guardian_email=form.guardian_email.data,
                plan=plan,
                order=order,
                billing_cycle=billing_cycle,
                payment_method_name=method.name,
                webpay_authorized=False,
            )

        except (ValueError, SQLAlchemyError) as e:
            db.session.rollback()
            flash(f"⚠️ {e}", "warning")
            return render_template("inscripcion.html", form=form, plan=plan, billing_cycle=billing_cycle)

        except Exception as e:
            db.session.rollback()
            flash(f"⚠️ Error inesperado: {e}", "danger")
            return render_template("inscripcion.html", form=form, plan=plan, billing_cycle=billing_cycle)

    # GET inicial o formulario no válido
    return render_template("inscripcion.html", form=form, plan=plan, billing_cycle=billing_cycle)

@bp.route("/reglamento")
def reglamento():
    return render_template("reglamento.html")