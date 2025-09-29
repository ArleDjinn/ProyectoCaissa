# services/catalog.py
from ..models import Plan, Workshop

def get_active_plans():
    """Devuelve planes activos ordenados por precio."""
    return Plan.query.filter_by(is_active=True).order_by(Plan.price_monthly).all()

def get_active_workshops():
    """Devuelve talleres activos ordenados por día y hora."""
    return (
        Workshop.query.filter_by(is_active=True)
        .order_by(Workshop.day_of_week, Workshop.start_time)
        .all()
    )
