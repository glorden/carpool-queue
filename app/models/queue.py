from sqlmodel import SQLModel, Field


class QueuePosition(SQLModel, table=True):
    """Текущее место пользователя в очереди.

    Чем меньше position, тем раньше человеку предложат заказ.
    Когда человек выполняет заказ, его position становится
    больше, чем у всех остальных (он уходит в конец).
    """

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", unique=True)
    position: int
