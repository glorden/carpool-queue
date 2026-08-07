"""Точечно выдаёт или снимает одну роль пользователю по username.

Основной инструмент для выдачи первой роли администратора после деплоя
миграции ролей — без этого некому было бы открыть страницу «Админ» (роль
admin никому не проставляется автоматически, см. ARCHITECTURE.md, «Роли
и права доступа»). Также общий аварийный путь на будущее, если
веб-интерфейс/сессия недоступны — тот же принцип, что у
scripts/add_user.py/reorder_queue.py.

Использование:
    python -m scripts.grant_role username driver|dispatcher|admin
    python -m scripts.grant_role username driver|dispatcher|admin --remove
"""
import sys

from sqlmodel import Session, select

from app.database import engine
from app.models.user import User

ROLE_FIELDS = {
    "driver": "is_driver",
    "dispatcher": "is_dispatcher",
    "admin": "is_admin",
}

args = sys.argv[1:]
remove = "--remove" in args
if remove:
    args.remove("--remove")

if len(args) != 2:
    print("Использование: python -m scripts.grant_role username driver|dispatcher|admin [--remove]")
    sys.exit(1)

username, role = args

if role not in ROLE_FIELDS:
    print(f"Роль должна быть driver, dispatcher или admin (получено: {role!r})")
    sys.exit(1)

with Session(engine) as session:
    user = session.exec(select(User).where(User.username == username)).first()
    if user is None:
        print(f"Пользователь с username={username!r} не найден")
        sys.exit(1)

    field = ROLE_FIELDS[role]
    setattr(user, field, not remove)
    session.add(user)
    session.commit()
    session.refresh(user)

    action = "снята" if remove else "выдана"
    print(f"{user.name} (id={user.id}, username={username}): роль «{role}» {action}")
