"""add google sub column to users

Revision ID: 20250305_01
Revises: 
Create Date: 2025-03-05 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20250305_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("google_sub", sa.String(length=255), nullable=True))
    op.create_index("ix_users_google_sub", "users", ["google_sub"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_google_sub", table_name="users")
    op.drop_column("users", "google_sub")
