# app/auth.py
import os
import secrets
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
from datetime import datetime, timezone
from .extensions import db, oauth

bp = Blueprint("auth", __name__, template_folder="templates")

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
    user.previous_login_at = user.last_login_at
    user.last_login_at = datetime.now(timezone.utc)
    db.session.commit()
    login_user(user)


def _get_google_client():
    google = oauth.create_client("google")
    if google is None:
        current_app.logger.error("No se pudo crear el cliente de Google OAuth.")
    return google

@bp.route("/login", methods=["GET", "POST"])
def login():
    next_param = request.args.get("next")
    show_google_help = bool(request.args.get("show_google_help"))
    google_login_url = None
    if _google_configured():
        if next_param:
            google_login_url = url_for("auth.google_start", next=next_param)
        else:
            google_login_url = url_for("auth.google_start")
        if request.method == "POST":
            return redirect(google_login_url)
    elif request.method == "POST":
        flash(
            "La autenticación con Google no está disponible en este momento.",
            "danger",
        )
    return render_template(
        "login.html",
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
        db.session.commit()
    else:
        user = User(
            email=email,
            name=userinfo.get("name") or email,
            google_sub=userinfo.get("sub"),
            _is_active=True,
        )
        user.set_password(secrets.token_urlsafe(32))
        user.activate()
        user.email_confirmed_at = datetime.now(timezone.utc)
        db.session.add(user)

    if not user.id:
        db.session.flush()
        db.session.commit()

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
