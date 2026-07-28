"""unique vk_id and drop password_hash on user

Revision ID: 6c16a556405e
Revises: 5437dcec06ba
Create Date: 2026-07-28 10:28:25.103882

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6c16a556405e'
down_revision: Union[str, Sequence[str], None] = '5437dcec06ba'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Автогенерация заодно предложила alter_column('order', 'status', VARCHAR ->
# Enum) — ложное срабатывание (SQLite хранит Enum как VARCHAR, нативного
# типа нет), к этой миграции не относится, убрано вручную.


def upgrade() -> None:
    """Upgrade schema."""
    # vk_id (уникальность) и password_hash (удаление) — обе операции на
    # user, обе требуют пересоздания таблицы на SQLite. Одно
    # batch_alter_table вместо двух подряд (см. ARCHITECTURE.md, Шаг 25).
    with op.batch_alter_table("user") as batch_op:
        batch_op.create_unique_constraint("uq_user_vk_id", ["vk_id"])
        batch_op.drop_column("password_hash")


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("user") as batch_op:
        batch_op.add_column(
            sa.Column(
                "password_hash", sa.VARCHAR(), nullable=False, server_default=""
            )
        )
        batch_op.drop_constraint("uq_user_vk_id", type_="unique")
