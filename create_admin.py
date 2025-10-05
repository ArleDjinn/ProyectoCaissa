# create_admin.py
from app import create_app, db
from app.models import User
from datetime import datetime, timezone

app = create_app()

with app.app_context():
    # Verificar si ya existe
    existing = User.query.filter_by(email="batman@caissa.cl").first()
    if existing:
        print("⚠️ El usuario admin ya existe:", existing)
    else:
        admin = User(
            email="batman@caissa.cl",
            name="Batman",
            is_admin=True
        )
        admin.set_password("IamBatman")
        admin.activate()
        admin.email_confirmed_at = datetime.now(timezone.utc)
        db.session.add(admin)
        db.session.commit()
        print("✅ Admin Batman creado correctamente.")