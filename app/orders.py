import json
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, session
from flask_login import login_required, current_user
from .extensions import db
from .models import Order, PaymentMethod, PaymentStatus, Plan, BillingCycle
from .services import orders as order_service
from .services import webpay as webpay_service

bp = Blueprint("orders", __name__, template_folder="templates")

@bp.route("/pago/<int:order_id>")
@login_required
def order_detail(order_id):
    order = Order.query.get_or_404(order_id)
    if current_user.is_admin:
        return render_template("order_detail.html", order=order)
    guardian_profile = getattr(current_user, "guardian_profile", None)
    if guardian_profile is None:
        abort(404)
    if order.subscription.guardian_id != guardian_profile.id:
        abort(403)
    return render_template("order_detail.html", order=order)

@bp.route("/pago/<int:order_id>/confirmar", methods=["POST"])
@login_required
def confirm_payment(order_id):
    order = Order.query.get_or_404(order_id)
    if not current_user.is_admin:
        abort(403)
    order_service.mark_order_paid(order)
    db.session.commit()   # ✅ commit único aquí
    flash("✅ Pago confirmado correctamente", "success")
    return redirect(url_for("orders.order_detail", order_id=order.id))

@bp.route("/pago/<int:order_id>/webpay/iniciar", methods=["GET", "POST"])
def start_webpay(order_id):
    order = Order.query.get_or_404(order_id)

    if order.payment_method != PaymentMethod.webpay:
        flash("La orden no está configurada para Webpay.", "warning")
        return redirect(url_for("orders.order_detail", order_id=order.id))

    if order.payment_status == PaymentStatus.paid:
        flash("La orden ya fue pagada, no es necesario iniciar Webpay nuevamente.", "info")
        return redirect(url_for("orders.order_detail", order_id=order.id))

    if order.payment_status == PaymentStatus.failed:
        flash(
            "El cobro con Webpay fue rechazado anteriormente. Por favor elige transferencia"
            " o pago presencial.",
            "warning",
        )
        return redirect(url_for("orders.order_detail", order_id=order.id))

    pending_context = session.get("webpay_inscription")
    if (not pending_context or pending_context.get("order_id") != order.id) and order.detail:
        try:
            detail_payload = json.loads(order.detail)
        except (TypeError, ValueError):
            detail_payload = None
        else:
            if detail_payload and detail_payload.get("order_id") == order.id:
                session["webpay_inscription"] = detail_payload
                pending_context = detail_payload

    if not pending_context or pending_context.get("order_id") != order.id:
        flash(
            "No se encontró la información necesaria para iniciar Webpay. Completa nuevamente la inscripción o contáctanos.",
            "warning",
        )
        return redirect(url_for("orders.order_detail", order_id=order.id))

    # Crear transacción en Webpay
    token, url = webpay_service.create_for_order(order)
    order.external_id = token
    db.session.commit()

    # Autopost del token a Webpay
    html = f"""
    <html><body onload="document.forms[0].submit()">
      <form action="{url}" method="POST">
        <input type="hidden" name="token_ws" value="{token}"/>
        <noscript>
          <p>Redirigiendo a Webpay...</p>
          <button type="submit">Continuar</button>
        </noscript>
      </form>
    </body></html>
    """
    return html

@bp.route("/pago/webpay/retorno", methods=["GET", "POST"])
def webpay_return():
    token = request.form.get("token_ws") or request.args.get("token_ws")
    if not token:
        flash("Falta token de Webpay.", "danger")
        return redirect(url_for("core.home"))

    order = Order.query.filter_by(external_id=token).first()
    if not order:
        flash("Orden no encontrada.", "danger")
        return redirect(url_for("core.home"))

    resp = webpay_service.commit_token(token)

    status = (resp.get("status") or "").upper()
    authorized = status == "AUTHORIZED" or resp.get("response_code") == 0

    context = session.pop("webpay_inscription", None)
    detail_payload = None
    if order.detail:
        try:
            detail_payload = json.loads(order.detail)
        except (TypeError, ValueError):
            detail_payload = None

    if (not context or context.get("order_id") != order.id) and detail_payload and detail_payload.get(
            "order_id") == order.id:
        context = detail_payload
    if authorized:
        order_service.mark_order_paid(order)

        guardian_email = order.subscription.guardian.user.email
        plan = order.subscription.plan
        billing_cycle = order.subscription.billing_cycle
        temporary_password = None

        if context:
            guardian_email = context.get("guardian_email") or guardian_email
            plan_id = context.get("plan_id")
            if plan_id:
                plan = db.session.get(Plan, plan_id) or plan
            billing_cycle_name = context.get("billing_cycle")
            if billing_cycle_name:
                try:
                    billing_cycle = BillingCycle[billing_cycle_name]
                except KeyError:
                    pass
            if "temporary_password" in context:
                temporary_password = context.get("temporary_password")
                if temporary_password:
                    order.subscription.guardian.user.set_password(temporary_password)

        if order.detail is not None:
            order.detail = None

        db.session.commit()

        return render_template(
            "inscripcion_confirmacion.html",
            guardian_email=guardian_email,
            plan=plan,
            order=order,
            billing_cycle=billing_cycle,
            payment_method_name=PaymentMethod.webpay.name,
            temporary_password=temporary_password,
            webpay_authorized=True,
        )

    order_service.mark_order_failed(order)

    if order.detail is not None:
        order.detail = None

    db.session.commit()

    error_message = resp.get("status") or resp.get("response_code")
    if isinstance(error_message, int):
        error_message = f"Código de respuesta: {error_message}"
    elif error_message:
        error_message = error_message.upper()

    else:
        error_message = "El pago fue rechazado o cancelado."

    plan = order.subscription.plan
    if context and context.get("plan_id"):
        plan = db.session.get(Plan, context.get("plan_id")) or plan

    return render_template(
        "webpay_error.html",
        order=order,
        plan=plan,
        error_message=error_message,
    )

@bp.route("/pago/<int:order_id>/revertir", methods=["POST"])
@login_required
def revert_payment(order_id):
    order = Order.query.get_or_404(order_id)
    order_service.mark_order_pending(order)
    db.session.commit()
    flash("⏪ Pago revertido, la orden vuelve a 'pendiente'", "info")
    return redirect(url_for("orders.order_detail", order_id=order.id))
