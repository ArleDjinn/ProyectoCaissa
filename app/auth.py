# app/auth.py
import math
import os
import secrets
import socket
from contextlib import contextmanager
from urllib.parse import urlparse

from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    flash,
    request,
    current_app,
    session,
)
from flask_login import login_user, logout_user, login_required

try:  # pragma: no cover - dependencia opcional
    from authlib.integrations.base_client.errors import OAuthError
except ModuleNotFoundError:  # pragma: no cover - fallback cuando Authlib no está disponible

    class OAuthError(Exception):
        """Excepción base para errores de OAuth cuando Authlib no está instalado."""

        pass
from .models import User
from .forms import (
    LoginForm,
    InitialPasswordForm,
    PasswordResetRequestForm,
    PasswordResetForm,
)
from datetime import datetime, timezone
from .extensions import db, mail, oauth
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from flask_mail import Message

bp = Blueprint("auth", __name__, template_folder="templates")

INITIAL_PASSWORD_PURPOSE = "initial-password"
PASSWORD_RESET_PURPOSE = "password-reset"

def _google_configured() -> bool:
    return bool(
        current_app.config.get("GOOGLE_CLIENT_ID")
        and current_app.config.get("GOOGLE_CLIENT_SECRET")
    )


def _allow_insecure_transport_if_needed() -> None:
    if (
        current_app.config.get("TESTING")
        or current_app.config.get("DEBUG")
        or current_app.config.get("PREFERRED_URL_SCHEME", "http") == "http"
    ):
        os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")


def _finalize_login(user: User) -> None:
    login_user(user)
    user.previous_login_at = user.last_login_at
    user.last_login_at = datetime.now(timezone.utc)
    db.session.commit()


def _get_google_client():
    google = oauth.create_client("google")
    if google is None:
        current_app.logger.error("No se pudo crear el cliente de Google OAuth.")
    return google

@bp.route("/login", methods=["GET", "POST"])
def login():
    form = LoginForm()
    next_param = request.args.get("next")
    show_google_help = bool(request.args.get("show_google_help"))
    google_login_url = None
    if _google_configured():
        if next_param:
            google_login_url = url_for("auth.google_start", next=next_param)
        else:
            google_login_url = url_for("auth.google_start")
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
            try:
                _finalize_login(user)
            except Exception as exc:
                current_app.logger.error(
                    "Error completando inicio de sesión para %s: %s",
                    user.email,
                    exc,
                    exc_info=True,
                )
                db.session.rollback()
                flash("Ocurrió un problema al iniciar sesión. Intenta nuevamente.", "danger")
                return render_template("login.html", form=form)
            next_page = next_param
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
    return render_template(
        "login.html",
        form=form,
        google_login_url=google_login_url,
        show_google_help=show_google_help,
    )

@bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Sesión cerrada con éxito", "info")
    return redirect(url_for("core.home"))


@bp.route("/google/start")
def google_start():
    if not _google_configured():
        flash(
            "La autenticación con Google no está configurada. Contacta al equipo de Proyecto Caissa.",
            "danger",
        )
        return redirect(url_for("auth.login"))

    _allow_insecure_transport_if_needed()

    google = _get_google_client()
    if google is None:
        flash(
            "La autenticación con Google no está disponible en este momento.",
            "danger",
        )
        return redirect(url_for("auth.login"))

    next_url = request.args.get("next")
    if next_url and urlparse(next_url).netloc != "":
        next_url = url_for("core.home")

    referrer = request.referrer
    if referrer:
        parsed_ref = urlparse(referrer)
        if parsed_ref.netloc and parsed_ref.netloc != request.host:
            referrer = None

    session["google_oauth_next"] = next_url or referrer or url_for("core.home")

    redirect_uri = (
        current_app.config.get("GOOGLE_REDIRECT_URI")
        or url_for("auth.google_callback", _external=True)
    )
    session["google_oauth_redirect_uri"] = redirect_uri

    try:
        return google.authorize_redirect(
            redirect_uri,
            prompt="select_account",
            access_type="offline",
            include_granted_scopes="true",
        )
    except (OAuthError, Exception) as exc:
        current_app.logger.error(
            "Error iniciando el flujo OAuth de Google: %s", exc, exc_info=True
        )
        flash("No pudimos redirigirte a Google. Intenta nuevamente.", "danger")
        return redirect(url_for("auth.login"))

@bp.route("/callback")
@bp.route("/google/callback")
def google_callback():
    if not _google_configured():
        flash("La autenticación con Google no está disponible.", "danger")
        return redirect(url_for("auth.login"))

    _allow_insecure_transport_if_needed()

    google = _get_google_client()
    if not google:
        flash("No se pudo conectar con Google.", "danger")
        return redirect(url_for("auth.login"))

    try:
        token_data = google.authorize_access_token()
    except Exception as exc:
        current_app.logger.error("Error al autorizar token de Google: %s", exc, exc_info=True)
        flash("No pudimos autenticar tu cuenta de Google. Intenta nuevamente.", "danger")
        return redirect(url_for("auth.login"))

    userinfo = (
        token_data.get("userinfo")
        or google.parse_id_token(token_data)
        or google.get("userinfo").json()
    )

    if not userinfo or not userinfo.get("email"):
        flash("No pudimos obtener tus datos de Google.", "danger")
        return redirect(url_for("auth.login"))

    email = userinfo["email"]
    if not userinfo.get("email_verified", True):
        flash("Tu correo de Google no está verificado.", "warning")
        return redirect(url_for("auth.login"))

    user = User.query.filter_by(email=email).first()
    if user:
        user.google_sub = userinfo.get("sub")
        user.name = userinfo.get("name") or user.name
        user.email_confirmed_at = user.email_confirmed_at or datetime.now(timezone.utc)
        user.activate()
    else:
        user = User(
            email=email,
            name=userinfo.get("name") or email,
            google_sub=userinfo.get("sub"),
        )
        user.set_password(secrets.token_urlsafe(32))
        user.activate()
        user.email_confirmed_at = datetime.now(timezone.utc)
        db.session.add(user)

    try:
        _finalize_login(user)
    except Exception as exc:
        current_app.logger.error("Error guardando sesión Google para %s: %s", email, exc, exc_info=True)
        db.session.rollback()
        flash("Error interno al crear la sesión.", "danger")
        return redirect(url_for("auth.login"))

    next_url = session.pop("google_oauth_next", None)
    if next_url and urlparse(next_url).netloc == "":
        return redirect(next_url)
    if user.is_admin:
        return redirect(url_for("admin.dashboard"))
    if user.guardian_profile:
        return redirect(url_for("portal.dashboard"))
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

@contextmanager
def _temporary_socket_timeout(timeout: int | None):
    if not timeout or timeout <= 0:
        yield
        return

    previous_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(timeout)
    try:
        yield
    finally:
        socket.setdefaulttimeout(previous_timeout)

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
    timeout = current_app.config.get("MAIL_SEND_TIMEOUT")
    with _temporary_socket_timeout(timeout):
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
            try:
                send_password_reset_email(user, token)
            except (Exception, SystemExit) as exc:
                current_app.logger.error(
                    "Error enviando correo de restablecimiento a %s: %s",
                    user.email,
                    exc,
                    exc_info=True,
                )
            else:
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