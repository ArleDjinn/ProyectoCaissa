# services/subscriptions.py
from ..models import Subscription, SubscriptionStatus, Plan, Guardian, BillingCycle
from ..extensions import db
from datetime import date

def create_subscription(guardian: Guardian, plan: Plan,
                        billing_cycle: BillingCycle = BillingCycle.monthly,
                        start_date: date = None) -> Subscription:
    sub = Subscription(
        guardian=guardian,
        plan=plan,
        billing_cycle=billing_cycle,
        start_date=start_date or date.today()
    )
    db.session.add(sub)
    return sub

def get_active_subscriptions(guardian: Guardian):
    return Subscription.query.filter_by(
        guardian_id=guardian.id, status=SubscriptionStatus.active
    ).all()

def cancel_subscription(sub: Subscription):
    sub.status = SubscriptionStatus.canceled
    return sub

def activate_subscription(sub: Subscription):
    sub.status = SubscriptionStatus.active
    return sub
