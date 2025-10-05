# app/auth.py
import math
from urllib.parse import urlparse

from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required
from .models import User
from .forms import (
    LoginForm,
    InitialPasswordForm,
    PasswordResetRequestForm,
    PasswordResetForm,
)
from datetime import datetime, timezone
from .extensions import db, mail
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from flask_mail import Message

bp = Blueprint("auth", __name__, template_folder="templates")

INITIAL_PASSWORD_PURPOSE = "initial-password"
PASSWORD_RESET_PURPOSE = "password-reset"

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


def _token_expiration_hours() -> int:
    max_age = current_app.config["INITIAL_PASSWORD_TOKEN_MAX_AGE"]
    return max(1, math.ceil(max_age / 3600))


def generate_password_reset_token(user: User) -> str:
    serializer = _get_serializer()
    return serializer.dumps({"user_id": user.id, "purpose": PASSWORD_RESET_PURPOSE})


def send_password_reset_email(user: User, token: str):
    reset_url = url_for("auth.reset_password", token=token, _external=True)
    expiration_hours = _token_expiration_hours()
    msg = Message(
        subject="Restablece tu contraseña de Proyecto Caissa",
        recipients=[user.email],
    )
    msg.body = render_template(
        "emails/password_reset.txt",
        user=user,
        reset_url=reset_url,
        expiration_hours=expiration_hours,
    )
    msg.html = render_template(
        "emails/password_reset.html",
        user=user,
        reset_url=reset_url,
        expiration_hours=expiration_hours,
    )
    mail.send(msg)

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
    purpose = data.get("purpose") if isinstance(data, dict) else None
    if purpose != INITIAL_PASSWORD_PURPOSE or not user_id:
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

@bp.route("/reset/solicitar", methods=["GET", "POST"])
def request_password_reset():
    form = PasswordResetRequestForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            token = generate_password_reset_token(user)
            user.set_password_reset_token(token)
            db.session.commit()
            send_password_reset_email(user, token)
            current_app.logger.info("Password reset email sent to %s", user.email)
        expiration_hours = _token_expiration_hours()
        hours_label = "hora" if expiration_hours == 1 else "horas"
        flash(
            f"Si el correo ingresado está registrado, enviaremos un enlace para restablecer la contraseña. "
            f"Recuerda que caduca en {expiration_hours} {hours_label}.",
            "info",
        )
        return redirect(url_for("auth.request_password_reset"))

    return render_template("auth/password_reset_request.html", form=form)

@bp.route("/reset/<token>", methods=["GET", "POST"])
def reset_password(token):
    form = PasswordResetForm()
    serializer = _get_serializer()
    max_age = current_app.config["INITIAL_PASSWORD_TOKEN_MAX_AGE"]

    try:
        data = serializer.loads(token, max_age=max_age)
    except SignatureExpired:
        flash("El enlace ha expirado. Solicita uno nuevo.", "warning")
        return render_template("auth/password_reset_invalid.html")
    except BadSignature:
        flash("El enlace de restablecimiento no es válido.", "danger")
        return render_template("auth/password_reset_invalid.html")

    user_id = data.get("user_id") if isinstance(data, dict) else None
    purpose = data.get("purpose") if isinstance(data, dict) else None
    if purpose != PASSWORD_RESET_PURPOSE or not user_id:
        flash("El enlace de restablecimiento no es válido.", "danger")
        return render_template("auth/password_reset_invalid.html")

    user = User.query.get(user_id)
    if not user or not user.verify_password_reset_token(token):
        flash("El enlace ya fue utilizado o es inválido.", "danger")
        return render_template("auth/password_reset_invalid.html")

    if form.validate_on_submit():
        user.set_password(form.password.data)
        user.clear_password_reset_token()
        db.session.commit()
        flash("Tu contraseña fue actualizada correctamente. Ya puedes iniciar sesión.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/password_reset_form.html", form=form, user=user)