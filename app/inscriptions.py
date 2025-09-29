from datetime import datetime, timezone

from flask import Blueprint, render_template, redirect, url_for, flash, request
from .forms import InscriptionForm, ChildForm
from .models import User, Plan, Workshop, BillingCycle, PaymentMethod, KnowledgeLevel, Subscription
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
            # Crear User
            user = User(name=form.guardian_name.data, email=form.guardian_email.data)
            user.set_password("temporal123")
            db.session.add(user)

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

            # 🚀 Si es Webpay, iniciamos el flujo
            if method == PaymentMethod.webpay:
                return redirect(url_for("orders.start_webpay", order_id=order.id))

            flash("✅ Inscripción creada, ahora confirma tu pago.", "success")
            return redirect(url_for("orders.order_detail", order_id=order.id))


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