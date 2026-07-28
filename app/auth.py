"""Текущий пользователь из серверной сессии. См. ARCHITECTURE.md,
«Вход через VK ID»."""
from fastapi import Depends, Request
from sqlmodel import Session

from app.database import get_session
from app.models.user import User


def get_current_user_optional(
    request: Request, session: Session = Depends(get_session)
) -> User | None:
    """Пользователь текущей сессии, или None, если вход не выполнен."""
    user_id = request.session.get("user_id")
    return session.get(User, user_id) if user_id else None
