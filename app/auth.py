# app/auth.py
from urllib.parse import urlparse

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required
from .models import User
from .forms import LoginForm
from datetime import datetime, timezone
from .extensions import db

bp = Blueprint("auth", __name__, template_folder="templates")

@bp.route("/login", methods=["GET", "POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and user.check_password(form.password.data):
            login_user(user)
            user.previous_login_at = user.last_login_at
            user.last_login_at = datetime.now(timezone.utc)
            db.session.commit()
            next_page = request.args.get("next")
            if next_page and urlparse(next_page).netloc == "":
                return redirect(next_page)
            if user.is_admin:
                return redirect(url_for("admin.dashboard"))
            if user.guardian_profile:
                return redirect(url_for("portal.dashboard"))

            logout_user()
            flash("Tu cuenta no tiene un portal asignado. Contáctanos para recibir ayuda.", "warning")
            return redirect(url_for("core.home"))
        flash("Credenciales inválidas", "danger")
    return render_template("login.html", form=form)

@bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Sesión cerrada con éxito", "info")
    return redirect(url_for("core.home"))
