from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from .extensions import db
from .models import Order, PaymentMethod
from .services import orders as order_service
from .services import webpay as webpay_service

bp = Blueprint("orders", __name__, template_folder="templates")

@bp.route("/pago/<int:order_id>")
def order_detail(order_id):
    order = Order.query.get_or_404(order_id)
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

    if authorized:
        order_service.mark_order_paid(order)
        db.session.commit()
        flash("✅ Pago autorizado en Webpay", "success")
    else:
        order_service.mark_order_failed(order)
        db.session.commit()
        flash("⚠️ Pago rechazado o fallido", "warning")

    return redirect(url_for("orders.order_detail", order_id=order.id))

@bp.route("/pago/<int:order_id>/revertir", methods=["POST"])
@login_required
def revert_payment(order_id):
    order = Order.query.get_or_404(order_id)
    order_service.mark_order_pending(order)
    db.session.commit()
    flash("⏪ Pago revertido, la orden vuelve a 'pendiente'", "info")
    return redirect(url_for("orders.order_detail", order_id=order.id))
