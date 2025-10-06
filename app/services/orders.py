# services/orders.py
from .subscriptions import activate_subscription
from ..models import (
    Order,
    PaymentMethod,
    PaymentStatus,
    Subscription,
    SubscriptionStatus,
    BillingCycle,
)
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


def calculate_subscription_amount(subscription: Subscription) -> int:
    """Retorna el monto correspondiente al ciclo de facturación de la suscripción."""
    plan = subscription.plan
    if subscription.billing_cycle == BillingCycle.monthly:
        return plan.price_monthly
    return int(
        plan.price_monthly
        * 3
        * (1 - (subscription.plan.quarterly_discount_pct / 100))
    )


def create_billing_cycle_order(
    subscription: Subscription, payment_method: PaymentMethod | None = None
) -> Order:
    """Crea una nueva orden para el siguiente ciclo de facturación de la suscripción."""
    method = payment_method or PaymentMethod.in_person
    amount = calculate_subscription_amount(subscription)
    return create_order(subscription, amount, method)

