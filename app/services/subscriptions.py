# services/subscriptions.py
from datetime import date

from ..models import (
    Subscription,
    SubscriptionStatus,
    Plan,
    Guardian,
    BillingCycle,
    EnrollmentStatus,
)
from ..extensions import db

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

def cancel_subscription(sub: Subscription, *, cancel_enrollments: bool = True, end_date: date | None = None):
    from . import enrollments as enrollment_service

    sub.status = SubscriptionStatus.canceled
    sub.end_date = end_date or date.today()
    if cancel_enrollments:
        for enrollment in sub.enrollments:
            if enrollment.status == EnrollmentStatus.active:
                enrollment_service.cancel_enrollment(enrollment)
    return sub

def activate_subscription(sub: Subscription):
    sub.status = SubscriptionStatus.active
    sub.end_date = None
    return sub
