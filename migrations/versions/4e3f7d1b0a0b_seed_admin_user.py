"""Seed default admin user

Revision ID: 4e3f7d1b0a0b
Revises: fb1d4cb95230
Create Date: 2024-05-20 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime, timezone
from werkzeug.security import generate_password_hash

# revision identifiers, used by Alembic.
revision = "4e3f7d1b0a0b"
down_revision = "fb1d4cb95230"
branch_labels = None
depends_on = None

ADMIN_EMAIL = "admin@caissa.cl"
ADMIN_PASSWORD = "Admin1234!"

def _users_table():
    return sa.table(
        "users",
        sa.column("id", sa.Integer()),
        sa.column("email", sa.String(length=120)),
        sa.column("name", sa.String(length=120)),
        sa.column("password_hash", sa.String(length=128)),
        sa.column("is_admin", sa.Boolean()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )

def upgrade():
    bind = op.get_bind()
    users = _users_table()
    existing = bind.execute(
        sa.select(users.c.id).where(users.c.email == ADMIN_EMAIL)
    ).first()

    if existing is None:
        now = datetime.now(timezone.utc)
        bind.execute(
            users.insert().values(
                email=ADMIN_EMAIL,
                name="Administrador Caissa",
                password_hash=generate_password_hash(ADMIN_PASSWORD),
                is_admin=True,
                created_at=now,
                updated_at=now,
            )
        )

def downgrade():
    users = _users_table()
    op.execute(users.delete().where(users.c.email == ADMIN_EMAIL))