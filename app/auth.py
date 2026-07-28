"""Текущий пользователь из серверной сессии. См. ARCHITECTURE.md,
«Вход через VK ID»."""
from fastapi import Depends, HTTPException, Request
from sqlmodel import Session

from app.database import get_session
from app.models.user import User


def get_current_user_optional(
    request: Request, session: Session = Depends(get_session)
) -> User | None:
    """Пользователь текущей сессии, или None, если вход не выполнен."""
    user_id = request.session.get("user_id")
    return session.get(User, user_id) if user_id else None


def get_current_user_required(
    user: User | None = Depends(get_current_user_optional),
) -> User:
    """Тот же пользователь, но 401 вместо None — для эндпоинтов, которым
    обязательна личность вызывающего (см. ARCHITECTURE.md, Шаг 26)."""
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user
