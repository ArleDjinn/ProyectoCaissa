from flask import Blueprint, render_template, redirect, url_for, flash, abort
from flask_login import login_required, current_user

from .models import Order, PaymentStatus, Subscription

bp = Blueprint("portal", __name__, template_folder="templates")


@bp.before_request
def ensure_guardian_access():
    if not current_user.is_authenticated:
        return None

    if current_user.is_admin:
        flash("Estás autenticado como administrador. Usa el panel correspondiente.", "info")
        return redirect(url_for("admin.dashboard"))

    if current_user.guardian_profile is None:
        flash("Tu cuenta no tiene un perfil de apoderado asociado.", "warning")
        return redirect(url_for("core.home"))


@bp.route("/")
@login_required
def dashboard():
    guardian = current_user.guardian_profile
    if guardian is None:
        abort(403)

    orders = (
        Order.query.join(Subscription)
        .filter(Subscription.guardian_id == guardian.id)
        .order_by(Order.created_at.desc())
        .all()
    )

    return render_template("portal/dashboard.html", orders=orders)