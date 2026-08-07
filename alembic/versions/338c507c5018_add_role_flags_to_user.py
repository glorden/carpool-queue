"""add role flags to user

Revision ID: 338c507c5018
Revises: 90893e2b4590
Create Date: 2026-08-07 09:48:27.985344

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '338c507c5018'
down_revision: Union[str, Sequence[str], None] = '90893e2b4590'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Автогенерация заодно предложила alter_column('order', 'status', VARCHAR ->
# Enum) — ложное срабатывание (SQLite хранит Enum как VARCHAR, нативного
# типа нет), к этой миграции не относится, убрано вручную (см. 6c16a556405e,
# та же особенность).


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("user") as batch_op:
        batch_op.add_column(
            sa.Column("is_driver", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(
            sa.Column("is_dispatcher", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(
            sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false())
        )

    # Бэкфилл по сегодняшней негласной конвенции (см. ARCHITECTURE.md, «Роли
    # и права доступа»): кто уже состоит хотя бы в одной очереди — водитель,
    # кто нет — диспетчер. is_admin никому не проставляется автоматически —
    # первого администратора выдаёт scripts/grant_role.py после деплоя.
    bind = op.get_bind()
    bind.execute(sa.text(
        "UPDATE user SET is_driver = 1 "
        "WHERE id IN (SELECT DISTINCT user_id FROM queueposition)"
    ))
    bind.execute(sa.text(
        "UPDATE user SET is_dispatcher = 1 "
        "WHERE id NOT IN (SELECT DISTINCT user_id FROM queueposition)"
    ))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("user") as batch_op:
        batch_op.drop_column("is_admin")
        batch_op.drop_column("is_dispatcher")
        batch_op.drop_column("is_driver")
