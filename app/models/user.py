from sqlmodel import SQLModel, Field


class User(SQLModel, table=True):
    """Один из 10 участников, кто может брать заказы."""

    id: int | None = Field(default=None, primary_key=True)
    name: str
    username: str = Field(unique=True, index=True)
    active: bool = Field(default=True)
    # active=False используем позже для "заморозки" (отпуск/болезнь) —
    # такому пользователю заказы предлагаться не будут
    vk_id: int | None = Field(default=None, unique=True)
    # id пользователя VK — источник входа (см. ARCHITECTURE.md, "Вход через
    # VK ID") и тег в уведомлениях. unique — это ключ входа, один VK-аккаунт
    # не может быть привязан к двум User
