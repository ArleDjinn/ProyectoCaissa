# services/enrollments.py
from ..models import Enrollment, EnrollmentStatus, Child, Workshop, Subscription
from ..extensions import db

def create_enrollment(subscription: Subscription, child: Child, workshop: Workshop) -> Enrollment:
    # --- Validar límite global (niños × talleres por niño) ---
    total_allowed = subscription.plan.max_children * subscription.plan.max_workshops_per_child
    if len(subscription.enrollments) >= total_allowed:
        raise ValueError("Límite global del plan superado")

    # --- Validar talleres por niño ---
    child_enrollments = [e for e in subscription.enrollments if e.child_id == child.id and e.status == EnrollmentStatus.active]
    if len(child_enrollments) >= subscription.plan.max_workshops_per_child:
        raise ValueError(f"Este plan solo permite {subscription.plan.max_workshops_per_child} taller(es) por niño")

    # --- Crear inscripción ---
    enrollment = Enrollment(
        subscription=subscription,
        child=child,
        workshop=workshop,
        status=EnrollmentStatus.active
    )
    db.session.add(enrollment)
    return enrollment

def move_enrollment(enrollment: Enrollment, new_workshop: Workshop):
    enrollment.status = EnrollmentStatus.changed
    new = Enrollment(
        subscription=enrollment.subscription,
        child=enrollment.child,
        workshop=new_workshop,
        status=EnrollmentStatus.active
    )
    db.session.add(new)
    return new

def cancel_enrollment(enrollment: Enrollment):
    enrollment.status = EnrollmentStatus.canceled
    return enrollment
