from enum import Enum

from sqlmodel import SQLModel, Field, UniqueConstraint


class QueueType(str, Enum):
    """Тип очереди — заказы каждого типа маршрутизируются независимо
    (см. ARCHITECTURE.md, «Логика очереди»)."""

    long = "long"    # дальние (межгородние) поездки
    short = "short"  # короткие поездки


class QueuePosition(SQLModel, table=True):
    """Текущее место пользователя в одной из очередей (см. QueueType).

    Один и тот же пользователь может одновременно состоять в обеих
    очередях с независимыми позициями — уникальность на пару
    (user_id, queue_type), не на один user_id.

    Чем меньше position, тем раньше человеку предложат заказ этого
    типа. Когда человек выполняет заказ, его position в
    соответствующей очереди становится больше, чем у всех остальных
    в ней же (он уходит в конец только этой очереди).
    """

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    queue_type: QueueType
    position: int

    __table_args__ = (
        UniqueConstraint(
            "user_id", "queue_type", name="uq_queueposition_user_id_queue_type"
        ),
    )
