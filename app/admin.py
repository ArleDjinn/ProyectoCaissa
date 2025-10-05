# app/admin.py
import math

from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, current_app
from flask_login import login_required, current_user
from sqlalchemy.orm import joinedload

from .forms import (
    PlanForm,
    WorkshopForm,
    GuardianAdminForm,
    ChildAdminForm,
    DeleteChildForm,
    MoveEnrollmentForm,
    CancelEnrollmentForm,
    SimpleCSRFForm,
)
from .services import admin as admin_service
from .services import enrollments as enrollment_service
from .services import guardians as guardian_service
from .services import subscriptions as subscription_service
from .models import (
    Child,
    Order,
    Enrollment,
    Workshop,
    Plan,
    EnrollmentStatus,
    PaymentStatus,
    User,
    Subscription,
    SubscriptionStatus,
    Guardian,
    KnowledgeLevel,
)
from .extensions import db
from .auth import generate_password_reset_token, send_password_reset_email

bp = Blueprint("admin", __name__, template_folder="templates")

@bp.before_request
def ensure_admin_permissions():
    if not current_user.is_authenticated:
        return None
    if not current_user.is_admin:
        flash("No tienes permisos para acceder a esta sección.", "warning")
        return redirect(url_for("core.home"))

# --- Home del dashboard: redirige a Pagos por defecto ---
@bp.route("/dashboard")
@login_required
def dashboard():
    return redirect(url_for("admin.dashboard_payments"))


# --- Pagos / Estado de inscripción ---
@bp.route("/dashboard/pagos")
@login_required
def dashboard_payments():
    # Nuevos niños desde el último login
    last_login = (
        current_user.previous_login_at
        if current_user.previous_login_at is not None
        else current_user.created_at
    )
    new_children = Child.query.filter(Child.created_at > last_login).all()

    # Órdenes pendientes
    pending_orders = Order.query.filter_by(payment_status=PaymentStatus.pending).all()
    paid_orders = Order.query.filter_by(payment_status=PaymentStatus.paid).all()
    reset_expiration_hours = max(1, math.ceil(current_app.config["INITIAL_PASSWORD_TOKEN_MAX_AGE"] / 3600))

    return render_template(
        "admin/dashboard_payments.html",
        pending_orders=pending_orders,
        paid_orders=paid_orders,
        new_children=new_children,
        last_login=last_login,
        reset_expiration_hours=reset_expiration_hours,
    )

@bp.route("/usuarios/<int:user_id>/reset-password", methods=["POST"])
@login_required
def trigger_password_reset(user_id):
    user = User.query.get_or_404(user_id)
    token = generate_password_reset_token(user)
    user.set_password_reset_token(token)
    db.session.commit()
    try:
        send_password_reset_email(user, token)
    except (Exception, SystemExit) as exc:
        current_app.logger.error(
            "Error enviando correo de restablecimiento a %s: %s",
            user.email,
            exc,
            exc_info=True,
        )
        flash(
            "No pudimos enviar el correo de restablecimiento en este momento. "
            "Contacta manualmente al usuario o inténtalo nuevamente más tarde.",
            "warning",
        )
    else:
        expiration_hours = max(1, math.ceil(current_app.config["INITIAL_PASSWORD_TOKEN_MAX_AGE"] / 3600))
        hours_label = "hora" if expiration_hours == 1 else "horas"
        flash(
            f"Se envió un enlace de restablecimiento a {user.email}. Caduca en {expiration_hours} {hours_label}.",
            "info",
        )
        current_app.logger.info(
            "Admin %s solicitó restablecimiento de contraseña para %s", current_user.email, user.email
        )
    return redirect(request.referrer or url_for("admin.dashboard_payments"))

# --- Suscripciones ---
@bp.route("/dashboard/subscriptions")
@login_required
def dashboard_subscriptions():
    subscriptions = (
        Subscription.query.options(
            joinedload(Subscription.guardian).joinedload(Guardian.user),
            joinedload(Subscription.plan),
        )
        .order_by(Subscription.created_at.desc())
        .all()
    )
    pending_orders_count = Order.query.filter_by(payment_status=PaymentStatus.pending).count()
    return render_template(
        "admin/dashboard_subscriptions.html",
        subscriptions=subscriptions,
        SubscriptionStatus=SubscriptionStatus,
        pending_orders_count=pending_orders_count,
    )


@bp.route("/dashboard/subscriptions/<int:subscription_id>", methods=["GET", "POST"])
@login_required
def subscription_detail(subscription_id):
    subscription = (
        Subscription.query.options(
            joinedload(Subscription.guardian).joinedload(Guardian.user),
            joinedload(Subscription.guardian).joinedload(Guardian.children),
            joinedload(Subscription.enrollments).joinedload(Enrollment.child),
            joinedload(Subscription.enrollments).joinedload(Enrollment.workshop),
            joinedload(Subscription.plan),
        )
        .filter_by(id=subscription_id)
        .first()
    )
    if subscription is None:
        abort(404)

    guardian = subscription.guardian
    workshops = (
        Workshop.query.filter_by(is_active=True)
        .order_by(Workshop.day_of_week, Workshop.start_time)
        .all()
    )
    workshop_choices = [
        (
            w.id,
            f"{w.name} — {w.day_of_week.value} {w.start_time.strftime('%H:%M')}"
            if w.start_time
            else f"{w.name} — {w.day_of_week.value}",
        )
        for w in workshops
    ]

    def _guardian_initial_data():
        return {
            "name": guardian.user.name,
            "email": guardian.user.email,
            "phone": guardian.phone,
            "allow_whatsapp_group": guardian.allow_whatsapp_group,
        }

    guardian_form = GuardianAdminForm(prefix="guardian", data=_guardian_initial_data())

    child_forms = {}
    delete_child_forms = {}
    for child in guardian.children:
        data = {
            "child_id": child.id,
            "name": child.name,
            "birthdate": child.birthdate,
            "knowledge_level": child.knowledge_level.name if child.knowledge_level else "",
            "health_info": child.health_info,
            "allow_media": child.allow_media,
        }
        form = ChildAdminForm(prefix=f"child-{child.id}", data=data)
        child_forms[child.id] = form
        delete_child_forms[child.id] = DeleteChildForm(prefix=f"delete-child-{child.id}", data={"child_id": child.id})

    new_child_form = ChildAdminForm(prefix="new_child")

    move_enrollment_forms = {}
    cancel_enrollment_forms = {}
    for enrollment in subscription.enrollments:
        if enrollment.status == EnrollmentStatus.active:
            move_form = MoveEnrollmentForm(prefix=f"move-{enrollment.id}", data={"enrollment_id": enrollment.id})
            move_form.new_workshop_id.choices = workshop_choices
            move_enrollment_forms[enrollment.id] = move_form

            cancel_form = CancelEnrollmentForm(prefix=f"cancel-{enrollment.id}", data={"enrollment_id": enrollment.id})
            cancel_enrollment_forms[enrollment.id] = cancel_form

    cancel_subscription_form = SimpleCSRFForm(prefix="cancel-subscription")
    activate_subscription_form = SimpleCSRFForm(prefix="activate-subscription")

    action = request.form.get("action") if request.method == "POST" else None

    if action == "update_guardian":
        guardian_form = GuardianAdminForm(prefix="guardian", formdata=request.form)
        if guardian_form.validate():
            guardian.user.name = guardian_form.name.data
            guardian.user.email = guardian_form.email.data
            guardian.phone = guardian_form.phone.data
            guardian.allow_whatsapp_group = bool(guardian_form.allow_whatsapp_group.data)
            db.session.commit()
            flash("✅ Datos de contacto actualizados", "success")
            return redirect(url_for("admin.subscription_detail", subscription_id=subscription.id))
        else:
            flash("Revisa los datos del apoderado.", "warning")

    elif action == "add_child":
        new_child_form = ChildAdminForm(prefix="new_child", formdata=request.form)
        if new_child_form.validate():
            knowledge_level = new_child_form.knowledge_level.data or None
            knowledge_level_enum = KnowledgeLevel[knowledge_level] if knowledge_level else None
            guardian_service.create_child(
                guardian=guardian,
                name=new_child_form.name.data,
                birthdate=new_child_form.birthdate.data,
                knowledge_level=knowledge_level_enum,
                health_info=new_child_form.health_info.data,
                allow_media=bool(new_child_form.allow_media.data),
            )
            db.session.commit()
            flash("✅ Niño/a agregado", "success")
            return redirect(url_for("admin.subscription_detail", subscription_id=subscription.id))
        else:
            flash("No se pudo agregar al niño/a, revisa los datos.", "warning")

    elif action == "update_child":
        child_key = next((k for k in request.form if k.endswith("-child_id")), None)
        if child_key is None:
            abort(400)
        try:
            child_id = int(request.form.get(child_key))
        except (TypeError, ValueError):
            abort(400)
        child = Child.query.filter_by(id=child_id, guardian_id=guardian.id).first()
        if child is None:
            abort(404)
        child_form = ChildAdminForm(prefix=child_key.rsplit("-", 1)[0], formdata=request.form)
        child_forms[child.id] = child_form
        if child_form.validate():
            knowledge_level = child_form.knowledge_level.data or None
            knowledge_level_enum = KnowledgeLevel[knowledge_level] if knowledge_level else None
            guardian_service.update_child(
                child,
                name=child_form.name.data,
                birthdate=child_form.birthdate.data,
                knowledge_level=knowledge_level_enum,
                health_info=child_form.health_info.data,
                allow_media=bool(child_form.allow_media.data),
            )
            db.session.commit()
            flash("✅ Datos del niño/a actualizados", "success")
            return redirect(url_for("admin.subscription_detail", subscription_id=subscription.id))
        else:
            flash("No se pudo actualizar al niño/a, revisa los datos.", "warning")

    elif action == "delete_child":
        child_key = next((k for k in request.form if k.endswith("-child_id")), None)
        if child_key is None:
            abort(400)
        try:
            child_id = int(request.form.get(child_key))
        except (TypeError, ValueError):
            abort(400)
        child = Child.query.filter_by(id=child_id, guardian_id=guardian.id).first()
        if child is None:
            abort(404)
        delete_form = DeleteChildForm(prefix=child_key.rsplit("-", 1)[0], formdata=request.form)
        delete_child_forms[child.id] = delete_form
        if delete_form.validate():
            guardian_service.delete_child(child)
            db.session.commit()
            flash("🗑️ Niño/a eliminado", "info")
            return redirect(url_for("admin.subscription_detail", subscription_id=subscription.id))
        else:
            flash("No se pudo eliminar al niño/a.", "warning")

    elif action == "move_enrollment":
        enrollment_key = next((k for k in request.form if k.endswith("-enrollment_id")), None)
        if enrollment_key is None:
            abort(400)
        try:
            enrollment_id = int(request.form.get(enrollment_key))
        except (TypeError, ValueError):
            abort(400)
        enrollment = Enrollment.query.filter_by(id=enrollment_id, subscription_id=subscription.id).first()
        if enrollment is None:
            abort(404)
        if enrollment.status != EnrollmentStatus.active:
            flash("La matrícula no está activa.", "warning")
            return redirect(url_for("admin.subscription_detail", subscription_id=subscription.id))
        move_form = MoveEnrollmentForm(prefix=enrollment_key.rsplit("-", 1)[0], formdata=request.form)
        move_form.new_workshop_id.choices = workshop_choices
        move_enrollment_forms[enrollment.id] = move_form
        if move_form.validate():
            new_workshop_id = move_form.new_workshop_id.data
            if new_workshop_id == enrollment.workshop_id:
                flash("El taller seleccionado es el mismo actual.", "warning")
            else:
                new_ws = Workshop.query.get_or_404(new_workshop_id)
                enrollment_service.move_enrollment(enrollment, new_ws)
                db.session.commit()
                flash("✅ Matrícula movida correctamente", "success")
                return redirect(url_for("admin.subscription_detail", subscription_id=subscription.id))
        else:
            flash("No se pudo mover la matrícula.", "warning")

    elif action == "cancel_enrollment":
        enrollment_key = next((k for k in request.form if k.endswith("-enrollment_id")), None)
        if enrollment_key is None:
            abort(400)
        try:
            enrollment_id = int(request.form.get(enrollment_key))
        except (TypeError, ValueError):
            abort(400)
        enrollment = Enrollment.query.filter_by(id=enrollment_id, subscription_id=subscription.id).first()
        if enrollment is None:
            abort(404)
        if enrollment.status != EnrollmentStatus.active:
            flash("La matrícula no está activa.", "warning")
            return redirect(url_for("admin.subscription_detail", subscription_id=subscription.id))
        cancel_form = CancelEnrollmentForm(prefix=enrollment_key.rsplit("-", 1)[0], formdata=request.form)
        cancel_enrollment_forms[enrollment.id] = cancel_form
        if cancel_form.validate():
            enrollment_service.cancel_enrollment(enrollment)
            db.session.commit()
            flash("🛑 Matrícula cancelada", "info")
            return redirect(url_for("admin.subscription_detail", subscription_id=subscription.id))
        else:
            flash("No se pudo cancelar la matrícula.", "warning")

    elif action == "cancel_subscription":
        cancel_subscription_form = SimpleCSRFForm(prefix="cancel-subscription", formdata=request.form)
        if cancel_subscription_form.validate():
            subscription_service.cancel_subscription(subscription)
            db.session.commit()
            flash("🛑 Suscripción cancelada", "info")
            return redirect(url_for("admin.subscription_detail", subscription_id=subscription.id))
        else:
            flash("No se pudo cancelar la suscripción.", "warning")

    elif action == "activate_subscription":
        activate_subscription_form = SimpleCSRFForm(prefix="activate-subscription", formdata=request.form)
        if activate_subscription_form.validate():
            subscription_service.activate_subscription(subscription)
            db.session.commit()
            flash("✅ Suscripción activada", "success")
            return redirect(url_for("admin.subscription_detail", subscription_id=subscription.id))
        else:
            flash("No se pudo reactivar la suscripción.", "warning")

    pending_orders_count = Order.query.filter_by(payment_status=PaymentStatus.pending).count()

    return render_template(
        "admin/subscription_detail.html",
        subscription=subscription,
        guardian_form=guardian_form,
        child_forms=child_forms,
        delete_child_forms=delete_child_forms,
        new_child_form=new_child_form,
        move_enrollment_forms=move_enrollment_forms,
        cancel_enrollment_forms=cancel_enrollment_forms,
        cancel_subscription_form=cancel_subscription_form,
        activate_subscription_form=activate_subscription_form,
        workshops=workshops,
        EnrollmentStatus=EnrollmentStatus,
        SubscriptionStatus=SubscriptionStatus,
        pending_orders_count=pending_orders_count,
    )
# --- Planes ---
@bp.route("/planes")
@login_required
def list_plans():
    plans = admin_service.get_all_plans()
    return render_template("admin/dashboard_plans.html", plans=plans)


@bp.route("/planes/nuevo", methods=["GET", "POST"])
@login_required
def new_plan():
    form = PlanForm()
    if form.validate_on_submit():
        admin_service.create_plan(form)
        db.session.commit()
        flash("✅ Plan creado", "success")
        return redirect(url_for("admin.list_plans"))
    return render_template("admin/plan_form.html", form=form)


@bp.route("/planes/<int:plan_id>/editar", methods=["GET", "POST"])
@login_required
def edit_plan(plan_id):
    plan = admin_service.get_plan(plan_id)
    form = PlanForm(obj=plan)
    if form.validate_on_submit():
        admin_service.update_plan(plan, form)
        db.session.commit()
        flash("✅ Plan actualizado", "success")
        return redirect(url_for("admin.list_plans"))
    return render_template("admin/plan_form.html", form=form)


@bp.route("/planes/<int:plan_id>/toggle", methods=["POST"])
@login_required
def toggle_plan(plan_id):
    plan = Plan.query.get_or_404(plan_id)
    plan.is_active = not plan.is_active
    db.session.commit()
    flash("✅ Estado del plan actualizado", "info")
    return redirect(url_for("admin.list_plans"))


@bp.route("/planes/<int:plan_id>/eliminar", methods=["POST"])
@login_required
def delete_plan(plan_id):
    plan = admin_service.get_plan(plan_id)
    admin_service.delete_plan(plan)
    db.session.commit()
    flash("🗑️ Plan eliminado", "info")
    return redirect(url_for("admin.list_plans"))


# --- Talleres ---
@bp.route("/talleres")
@login_required
def list_workshops():
    workshops = admin_service.get_all_workshops()
    return render_template("admin/dashboard_workshops.html", workshops=workshops)


@bp.route("/talleres/nuevo", methods=["GET", "POST"])
@login_required
def new_workshop():
    form = WorkshopForm()
    if form.validate_on_submit():
        admin_service.create_workshop(form)
        db.session.commit()
        flash("✅ Taller creado", "success")
        return redirect(url_for("admin.list_workshops"))
    return render_template("admin/workshop_form.html", form=form)


@bp.route("/talleres/<int:workshop_id>/editar", methods=["GET", "POST"])
@login_required
def edit_workshop(workshop_id):
    workshop = admin_service.get_workshop(workshop_id)
    form = WorkshopForm(obj=workshop)
    if form.validate_on_submit():
        admin_service.update_workshop(workshop, form)
        db.session.commit()
        flash("✅ Taller actualizado", "success")
        return redirect(url_for("admin.list_workshops"))
    return render_template("admin/workshop_form.html", form=form)


@bp.route("/talleres/<int:workshop_id>/toggle", methods=["POST"])
@login_required
def toggle_workshop(workshop_id):
    ws = Workshop.query.get_or_404(workshop_id)
    ws.is_active = not ws.is_active
    db.session.commit()
    flash("✅ Estado del taller actualizado", "info")
    return redirect(url_for("admin.list_workshops"))


@bp.route("/talleres/<int:workshop_id>/eliminar", methods=["POST"])
@login_required
def delete_workshop(workshop_id):
    workshop = admin_service.get_workshop(workshop_id)
    admin_service.delete_workshop(workshop)
    db.session.commit()
    flash("🗑️ Taller eliminado", "info")
    return redirect(url_for("admin.list_workshops"))
