# app/admin.py
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from .forms import PlanForm, WorkshopForm
from .services import admin as admin_service
from .services import enrollments as enrollment_service
from .models import (
    Child,
    Order,
    Enrollment,
    Workshop,
    Plan,
    EnrollmentStatus,
    PaymentStatus,
)
from .extensions import db

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

    return render_template(
        "admin/dashboard_payments.html",
        pending_orders=pending_orders,
        paid_orders=paid_orders,
        new_children=new_children,
        last_login=last_login,
    )

# --- Gestión de matrículas ---
@bp.route("/dashboard/enrollments")
@login_required
def dashboard_enrollments():
    enrollments = Enrollment.query.filter_by(status=EnrollmentStatus.active).all()
    workshops = Workshop.query.filter_by(is_active=True).all()
    return render_template(
        "admin/dashboard_enrollments.html",
        enrollments=enrollments,
        workshops=workshops,
    )


@bp.route("/dashboard/enrollments/<int:enrollment_id>/move", methods=["POST"])
@login_required
def move_enrollment(enrollment_id):
    new_workshop_id = int(request.form.get("new_workshop_id"))
    enrollment = Enrollment.query.get_or_404(enrollment_id)
    new_ws = Workshop.query.get_or_404(new_workshop_id)

    enrollment_service.move_enrollment(enrollment, new_ws)
    db.session.commit()
    flash("✅ Matrícula movida correctamente", "success")
    return redirect(url_for("admin.dashboard_enrollments"))


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
