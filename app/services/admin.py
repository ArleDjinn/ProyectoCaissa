# services/admin.py
from ..models import Plan, Workshop, DayOfWeek
from ..extensions import db

# --------- Planes ---------
def get_all_plans():
    return Plan.query.order_by(Plan.name).all()

def create_plan(form):
    plan = Plan(
        name=form.name.data,
        max_children=form.max_children.data,
        max_workshops_per_child=form.max_workshops_per_child.data,
        price_monthly=form.price_monthly.data,
        is_active=form.is_active.data,
    )
    db.session.add(plan)
    return plan

def get_plan(plan_id):
    return Plan.query.get_or_404(plan_id)

def update_plan(plan, form):
    plan.name = form.name.data
    plan.max_children = form.max_children.data
    plan.max_workshops_per_child = form.max_workshops_per_child.data
    plan.price_monthly = form.price_monthly.data
    plan.is_active = form.is_active.data
    return plan

def delete_plan(plan):
    db.session.delete(plan)

# --------- Talleres ---------
def get_all_workshops():
    return Workshop.query.order_by(Workshop.day_of_week, Workshop.start_time).all()

def create_workshop(form):
    workshop = Workshop(
        name=form.name.data,
        day_of_week=DayOfWeek[form.day_of_week.data],
        start_time=form.start_time.data,
        end_time=form.end_time.data,
        is_active=form.is_active.data,
    )
    db.session.add(workshop)
    return workshop

def get_workshop(workshop_id):
    return Workshop.query.get_or_404(workshop_id)

def update_workshop(workshop, form):
    workshop.name = form.name.data
    workshop.day_of_week = DayOfWeek[form.day_of_week.data]
    workshop.start_time = form.start_time.data
    workshop.end_time = form.end_time.data
    workshop.is_active = form.is_active.data
    return workshop

def delete_workshop(workshop):
    db.session.delete(workshop)