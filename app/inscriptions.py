from datetime import datetime, timezone
from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user
from .forms import InscriptionForm, ChildForm
from .models import Plan, Workshop, BillingCycle, PaymentMethod, KnowledgeLevel, Subscription
from .extensions import db
from .services import guardians as guardian_service
from .services import subscriptions as subscription_service
from .services import enrollments as enrollment_service
from .services import orders as order_service
from sqlalchemy.exc import SQLAlchemyError

bp = Blueprint("inscriptions", __name__, template_folder="templates")

@bp.route("/inscripcion/<int:plan_id>", methods=["GET", "POST"])
def inscripcion(plan_id):

    plan = Plan.query.get_or_404(plan_id)
    if not current_user.is_authenticated:
        flash(
            "Para inscribir a tu hijo primero debes iniciar sesión con tu cuenta de Google. "
            "Presiona \"Continuar con Google\" para crear o acceder a tu cuenta y luego volveremos a esta inscripción automáticamente.",
            "info",
        )
        return redirect(
            url_for(
                "auth.login",
                next=request.url,
                show_google_help="1",
            )
        )

    form = InscriptionForm()
    form.guardian_email.data = current_user.email
    form.guardian_name.data = current_user.name

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

    if current_user.guardian_profile:
        flash(
            "Ya existe una inscripción asociada a tu cuenta. Contáctanos si necesitas actualizarla.",
            "warning",
        )
        return render_template("inscripcion.html", form=form, plan=plan, billing_cycle=billing_cycle)

    if form.validate_on_submit():
        user = current_user

        try:
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

            if method == PaymentMethod.webpay:
                session["webpay_inscription"] = {
                    "order_id": order.id,
                }
                return redirect(url_for("orders.start_webpay", order_id=order.id))

            flash(
                "✅ Inscripción creada correctamente.",
                "success",
            )

            return render_template(
                "inscripcion_confirmacion.html",
                guardian_email=user.email,
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