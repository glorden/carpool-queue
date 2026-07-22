"""Добавляет одного пользователя в очередь (в конец).

Использование:
    python -m scripts.add_user "Имя Фамилия" username
"""
import sys

from sqlmodel import Session, select

from app.database import engine
from app.models.user import User
from app.models.queue import QueuePosition

if len(sys.argv) != 3:
    print("Использование: python -m scripts.add_user \"Имя\" username")
    sys.exit(1)

name, username = sys.argv[1], sys.argv[2]

with Session(engine) as session:
    existing = session.exec(select(User).where(User.username == username)).first()
    if existing is not None:
        print(f"Пользователь с username={username!r} уже существует (id={existing.id})")
        sys.exit(1)

    user = User(name=name, username=username, password_hash="")
    session.add(user)
    session.commit()
    session.refresh(user)

    max_position = session.exec(
        select(QueuePosition.position).order_by(QueuePosition.position.desc())
    ).first()
    next_position = (max_position or 0) + 1

    session.add(QueuePosition(user_id=user.id, position=next_position))
    session.commit()

    print(f"Добавлен: {user.name} (id={user.id}, username={username}), позиция {next_position}")
