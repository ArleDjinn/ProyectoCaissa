# services/orders.py
from .subscriptions import activate_subscription
from ..models import Order, PaymentMethod, PaymentStatus, Subscription, SubscriptionStatus
from ..extensions import db

def create_order(subscription: Subscription, amount_clp: int,
                 method: PaymentMethod = PaymentMethod.in_person) -> Order:
    order = Order(
        subscription=subscription,
        amount_clp=amount_clp,
        payment_method=method,
        payment_status=PaymentStatus.pending
    )
    db.session.add(order)
    return order

def mark_order_paid(order: Order):
    order.payment_status = PaymentStatus.paid
    if order.subscription.status.name == "pending":
        activate_subscription(order.subscription)  # solo cambia el estado
    return order

def mark_order_failed(order: Order):
    order.payment_status = PaymentStatus.failed
    return order

def mark_order_pending(order: Order):
    """Reabre la orden (por ejemplo, si se confirmó por error)."""
    order.payment_status = PaymentStatus.pending
    return order

