from datetime import datetime

from sqlmodel import SQLModel, Field


class PriceItem(SQLModel, table=True):
    """Одна позиция прайс-листа (тур, направление, тариф)."""

    id: int | None = Field(default=None, primary_key=True)
    category: str  # "tour" | "direction" | "business" | "minivan"
    name: str
    price_text: str  # свободный текст: "1 234 ₽" или "99 руб/км"


class PriceLogEntry(SQLModel, table=True):
    """Лог изменений прайса — кто/когда/что сделал."""

    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    user_id: int = Field(foreign_key="user.id")
    action: str  # "created" | "updated" | "deleted"
    item_name: str  # снэпшот названия — переживает удаление позиции
    old_value: str | None = None
    new_value: str | None = None
