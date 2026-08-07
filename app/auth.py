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


def require_driver(current_user: User = Depends(get_current_user_required)) -> User:
    """403, если у пользователя нет роли водителя (и он не админ). См.
    ARCHITECTURE.md, «Роли и права доступа» — is_admin проходит любую
    ролевую проверку независимо от остальных флагов."""
    if not (current_user.is_driver or current_user.is_admin):
        raise HTTPException(status_code=403, detail="Driver role required")
    return current_user


def require_dispatcher(current_user: User = Depends(get_current_user_required)) -> User:
    """403, если у пользователя нет роли диспетчера (и он не админ)."""
    if not (current_user.is_dispatcher or current_user.is_admin):
        raise HTTPException(status_code=403, detail="Dispatcher role required")
    return current_user


def require_admin(current_user: User = Depends(get_current_user_required)) -> User:
    """403, если пользователь не администратор."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin role required")
    return current_user
