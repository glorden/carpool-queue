"""add queue_type to order and queueposition

Revision ID: 5437dcec06ba
Revises: ed3788bb5a0a
Create Date: 2026-07-23 16:05:00.013543

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '5437dcec06ba'
down_revision: Union[str, Sequence[str], None] = 'ed3788bb5a0a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Исходная миграция (4cc9dd7701d8) создала UNIQUE(user_id) на queueposition
# без имени — SQLite хранит его как анонимный inline UNIQUE (проверено на
# реальной carpool.db: inspector.get_unique_constraints даёт {'name': None,
# 'column_names': ['user_id']}). Чтобы drop_constraint нашёл его при
# рефлексии внутри batch_alter_table, нужно явно задать naming_convention.
NAMING_CONVENTION = {"uq": "uq_%(table_name)s_%(column_0_name)s"}


def upgrade() -> None:
    """Upgrade schema."""
    # --- order.queue_type: добавить nullable, забэкфилить, затянуть NOT
    #     NULL. SQLite не поддерживает ALTER COLUMN напрямую — смена
    #     nullable тоже требует batch mode (пересоздание таблицы). ---
    op.add_column(
        "order",
        sa.Column("queue_type", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )
    op.execute('UPDATE "order" SET queue_type = \'long\' WHERE queue_type IS NULL')
    with op.batch_alter_table("order") as batch_op:
        batch_op.alter_column(
            "queue_type",
            existing_type=sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
        )

    # --- queueposition.queue_type: добавить nullable, забэкфилить 'long'
    #     для всех существующих позиций (это и есть текущая единственная
    #     очередь дальних поездок) ---
    op.add_column(
        "queueposition",
        sa.Column("queue_type", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )
    op.execute("UPDATE queueposition SET queue_type = 'long' WHERE queue_type IS NULL")

    # --- снять старый анонимный UNIQUE(user_id), поставить составной
    #     UNIQUE(user_id, queue_type), затянуть NOT NULL — одним
    #     пересозданием таблицы ---
    with op.batch_alter_table(
        "queueposition", naming_convention=NAMING_CONVENTION
    ) as batch_op:
        batch_op.drop_constraint("uq_queueposition_user_id", type_="unique")
        batch_op.alter_column(
            "queue_type",
            existing_type=sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
        )
        batch_op.create_unique_constraint(
            "uq_queueposition_user_id_queue_type", ["user_id", "queue_type"]
        )

    # --- клонировать состав дальней очереди в короткую: тот же состав
    #     людей и тот же порядок на старте, дальше обе живут независимо
    #     (см. ARCHITECTURE.md). Только после смены constraint выше —
    #     со старым UNIQUE(user_id) вставка второй строки с тем же
    #     user_id упала бы на первой же записи. ---
    op.execute(
        "INSERT INTO queueposition (user_id, queue_type, position) "
        "SELECT user_id, 'short', position FROM queueposition WHERE queue_type = 'long'"
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Необратимо теряет: расхождение короткой очереди от длинной, если
    # оно уже накопилось за время работы, и метки типа у всех заказов —
    # тот же принцип, что и downgrade в 197ca095088c (там тоже безвозвратно
    # дропаются данные), для этого масштаба это ожидаемо.
    op.execute("DELETE FROM queueposition WHERE queue_type = 'short'")

    with op.batch_alter_table(
        "queueposition", naming_convention=NAMING_CONVENTION
    ) as batch_op:
        batch_op.drop_constraint(
            "uq_queueposition_user_id_queue_type", type_="unique"
        )
        batch_op.drop_column("queue_type")
        batch_op.create_unique_constraint("uq_queueposition_user_id", ["user_id"])

    with op.batch_alter_table("order") as batch_op:
        batch_op.drop_column("queue_type")
