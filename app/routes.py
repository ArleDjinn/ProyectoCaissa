#app/routes.py
from flask import Blueprint, render_template
from .services import catalog

bp = Blueprint("core", __name__, template_folder="templates")

@bp.route("/")
def home():
    planes = catalog.get_active_plans()
    talleres = catalog.get_active_workshops()
    return render_template("home.html", planes=planes, talleres=talleres)

@bp.route("/terminos")
def terms():
    return render_template("legal/terms.html")

@bp.route("/privacidad")
def privacy():
    return render_template("legal/privacy.html")