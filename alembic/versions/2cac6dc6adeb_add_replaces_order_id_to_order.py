"""add replaces_order_id to order

Revision ID: 2cac6dc6adeb
Revises: 338c507c5018
Create Date: 2026-08-08 00:04:11.714155

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2cac6dc6adeb'
down_revision: Union[str, Sequence[str], None] = '338c507c5018'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Автогенерация заодно предложила alter_column('order', 'status', VARCHAR ->
# Enum) — та же ложная находка, что и в 90893e2b4590/6c16a556405e (SQLite
# хранит Enum как VARCHAR, нативного типа нет), убрано вручную.
#
# Первый self-referential FK в проекте (order.replaces_order_id -> order.id).


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("order") as batch_op:
        batch_op.add_column(sa.Column("replaces_order_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_order_replaces_order_id_order", "order", ["replaces_order_id"], ["id"]
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("order") as batch_op:
        batch_op.drop_constraint("fk_order_replaces_order_id_order", type_="foreignkey")
        batch_op.drop_column("replaces_order_id")
