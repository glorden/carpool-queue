from datetime import date, datetime
from enum import Enum

from sqlmodel import SQLModel, Field

from app.models.queue import QueueType


class OrderStatus(str, Enum):
    pending = "pending"        # только создан, ещё никому не назначен
    assigned = "assigned"      # кто-то согласился и везёт
    completed = "completed"    # поездка завершена
    cancelled = "cancelled"    # заказ отменён (до или после назначения)


class OfferResponse(str, Enum):
    pending = "pending"    # ещё не ответил
    accepted = "accepted"
    declined = "declined"


class Order(SQLModel, table=True):
    """Заказ на поездку (дальнюю или короткую — см. QueueType)."""

    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    route: str | None = None
    comment: str | None = None
    status: OrderStatus = Field(default=OrderStatus.pending)
    queue_type: QueueType
    assigned_to: int | None = Field(default=None, foreign_key="user.id")
    completed_at: datetime | None = None
    self_assign_reason: str | None = None


class OrderOffer(SQLModel, table=True):
    """История предложений заказа конкретным людям по очереди.

    На один Order может быть несколько OrderOffer подряд —
    по одному на каждого, кому предлагали, пока кто-то не согласится.
    """

    id: int | None = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="order.id")
    user_id: int = Field(foreign_key="user.id")
    offered_at: datetime = Field(default_factory=datetime.utcnow)
    response: OfferResponse = Field(default=OfferResponse.pending)
    responded_at: datetime | None = None
