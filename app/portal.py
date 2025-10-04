import json

from flask import Blueprint, render_template, redirect, url_for, flash, session, abort
from flask_login import login_required, current_user

from .extensions import db
from .models import Order, PaymentMethod, PaymentStatus, Subscription

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


@bp.route("/ordenes/<int:order_id>/webpay/reintentar", methods=["POST"])
@login_required
def prepare_webpay_retry(order_id):
    guardian = current_user.guardian_profile
    if guardian is None:
        abort(403)

    order = Order.query.get_or_404(order_id)

    if order.subscription.guardian_id != guardian.id:
        abort(404)

    if order.payment_method != PaymentMethod.webpay:
        flash("Esta orden no utiliza Webpay.", "warning")
        return redirect(url_for("portal.dashboard"))

    if order.payment_status == PaymentStatus.paid:
        flash("La orden ya fue pagada, no es necesario reintentar el cobro.", "info")
        return redirect(url_for("portal.dashboard"))

    context = {
        "order_id": order.id,
        "guardian_email": guardian.user.email,
        "plan_id": order.subscription.plan_id,
        "billing_cycle": order.subscription.billing_cycle.name,
    }

    session["webpay_inscription"] = context
    order.detail = json.dumps(context)
    db.session.commit()

    flash("Estamos reconstruyendo la información y redirigiéndote a Webpay…", "info")
    return redirect(url_for("orders.start_webpay", order_id=order.id))