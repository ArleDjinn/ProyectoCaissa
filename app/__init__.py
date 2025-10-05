from pathlib import Path

from dotenv import load_dotenv
from flask import Flask

from .extensions import db, migrate, csrf, login_manager, mail
from .models import User
from . import admin, inscriptions, orders, portal

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=False)
load_dotenv(BASE_DIR / "instance" / ".env", override=False)

def create_app(config_class="config.Config"):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Inicializar extensiones
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    login_manager.init_app(app)
    mail.init_app(app)

    # Cargar usuario
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Registrar blueprints
    from . import routes, auth, admin
    app.register_blueprint(routes.bp)
    app.register_blueprint(auth.bp, url_prefix="/auth")
    app.register_blueprint(admin.bp, url_prefix="/admin")
    app.register_blueprint(portal.bp, url_prefix="/portal")
    app.register_blueprint(inscriptions.bp)
    app.register_blueprint(orders.bp)

    from datetime import datetime, timezone

    @app.context_processor
    def inject_current_year():
        return {"current_year": datetime.now(timezone.utc).year}

    return app
