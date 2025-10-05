# app/auth.py
from urllib.parse import urlparse

from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required
from .models import User
from .forms import LoginForm, InitialPasswordForm
from datetime import datetime, timezone
from .extensions import db
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

bp = Blueprint("auth", __name__, template_folder="templates")

@bp.route("/login", methods=["GET", "POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and user.check_password(form.password.data):
            if not user.is_active():
                flash(
                    "Tu cuenta aún no ha sido activada. Revisa tu correo para confirmar tu contraseña.",
                    "warning",
                )
                return render_template("login.html", form=form)
            if not user.email_confirmed_at:
                flash(
                    "Debes confirmar tu correo antes de iniciar sesión. Usa el enlace enviado por correo.",
                    "warning",
                )
                return render_template("login.html", form=form)
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

def _get_serializer() -> URLSafeTimedSerializer:
    secret_key = current_app.config["SECRET_KEY"]
    salt = current_app.config["INITIAL_PASSWORD_TOKEN_SALT"]
    return URLSafeTimedSerializer(secret_key, salt=salt)


@bp.route("/confirmar/<token>", methods=["GET", "POST"])
def confirm_initial_password(token):
    form = InitialPasswordForm()
    serializer = _get_serializer()
    max_age = current_app.config["INITIAL_PASSWORD_TOKEN_MAX_AGE"]

    try:
        data = serializer.loads(token, max_age=max_age)
    except SignatureExpired:
        flash("El enlace ha expirado. Solicita uno nuevo al equipo de Proyecto Caissa.", "warning")
        return render_template("auth/initial_password_invalid.html")
    except BadSignature:
        flash("El enlace de confirmación no es válido.", "danger")
        return render_template("auth/initial_password_invalid.html")

    user_id = data.get("user_id") if isinstance(data, dict) else None
    if not user_id:
        flash("El enlace recibido no es válido.", "danger")
        return render_template("auth/initial_password_invalid.html")

    user = User.query.get(user_id)
    if not user or not user.verify_password_reset_token(token):
        flash("El enlace ya fue utilizado o es inválido.", "danger")
        return render_template("auth/initial_password_invalid.html")

    if user.email_confirmed_at and user.is_active():
        flash("La cuenta ya fue confirmada. Inicia sesión con tu correo y contraseña.", "info")
        return redirect(url_for("auth.login"))

    if form.validate_on_submit():
        user.set_password(form.password.data)
        user.clear_password_reset_token()
        user.activate()
        user.email_confirmed_at = datetime.now(timezone.utc)
        db.session.commit()
        flash("Tu contraseña fue creada correctamente. Ya puedes iniciar sesión.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/initial_password_form.html", form=form, user=user)