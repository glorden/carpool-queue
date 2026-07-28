"""add created_by to order

Revision ID: 90893e2b4590
Revises: 6c16a556405e
Create Date: 2026-07-28 16:43:28.610142

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '90893e2b4590'
down_revision: Union[str, Sequence[str], None] = '6c16a556405e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Автогенерация заодно предложила alter_column('order', 'status', VARCHAR ->
# Enum) — ложное срабатывание (SQLite хранит Enum как VARCHAR, нативного
# типа нет), к этой миграции не относится, убрано вручную (см. 6c16a556405e,
# та же особенность).


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("order") as batch_op:
        batch_op.add_column(sa.Column("created_by", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_order_created_by_user", "user", ["created_by"], ["id"]
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("order") as batch_op:
        batch_op.drop_constraint("fk_order_created_by_user", type_="foreignkey")
        batch_op.drop_column("created_by")
