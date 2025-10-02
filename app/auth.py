# app/auth.py
from flask import Blueprint, render_template, redirect, url_for, flash
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
            if not user.is_admin:
                flash("Solo el personal autorizado puede acceder al panel de administración.", "warning")
                return redirect(url_for("core.home"))

            login_user(user)
            user.last_login_at = datetime.now(timezone.utc)
            db.session.commit()
            return redirect(url_for("admin.dashboard"))
        flash("Credenciales inválidas", "danger")
    return render_template("login.html", form=form)

@bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Sesión cerrada con éxito", "info")
    return redirect(url_for("core.home"))
