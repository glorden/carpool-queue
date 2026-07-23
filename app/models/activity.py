from datetime import datetime

from sqlmodel import SQLModel, Field


class ActivityLog(SQLModel, table=True):
    """Журнал действий — хронология событий системы, отдельная от Order
    (см. ARCHITECTURE.md). Не заменяет историю заказов, а дополняет её
    событиями вроде предложений и переходов в очереди."""

    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    user_id: int | None = Field(default=None, foreign_key="user.id")
    order_id: int | None = Field(default=None, foreign_key="order.id")
    event_type: str
    message: str
