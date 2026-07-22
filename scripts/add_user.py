"""Добавляет одного пользователя.

По умолчанию ставит его в конец очереди (обычный водитель).
С флагом --no-queue создаёт пользователя без очереди — для
диспетчеров/админов, которые создают заказы, но сами в очереди
водителей не участвуют.

Использование:
    python -m scripts.add_user "Имя Фамилия" username [--no-queue]
"""
import sys

from sqlmodel import Session, select

from app.database import engine
from app.models.user import User
from app.models.queue import QueuePosition

args = sys.argv[1:]
no_queue = "--no-queue" in args
if no_queue:
    args.remove("--no-queue")

if len(args) != 2:
    print("Использование: python -m scripts.add_user \"Имя\" username [--no-queue]")
    sys.exit(1)

name, username = args

with Session(engine) as session:
    existing = session.exec(select(User).where(User.username == username)).first()
    if existing is not None:
        print(f"Пользователь с username={username!r} уже существует (id={existing.id})")
        sys.exit(1)

    user = User(name=name, username=username, password_hash="")
    session.add(user)
    session.commit()
    session.refresh(user)

    if no_queue:
        print(f"Добавлен: {user.name} (id={user.id}, username={username}), без очереди (диспетчер)")
    else:
        max_position = session.exec(
            select(QueuePosition.position).order_by(QueuePosition.position.desc())
        ).first()
        next_position = (max_position or 0) + 1

        session.add(QueuePosition(user_id=user.id, position=next_position))
        session.commit()

        print(f"Добавлен: {user.name} (id={user.id}, username={username}), позиция {next_position}")
