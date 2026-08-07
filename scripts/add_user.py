"""Добавляет одного пользователя.

По умолчанию — водитель (роль is_driver), ставится в конец обеих очередей
(возит и дальние, и короткие поездки). С флагом --queue-type=long|short
добавляется только в одну из очередей. С флагом --no-queue создаётся
диспетчер (роль is_dispatcher) без очереди — создаёт и назначает заказы,
но сам в очереди водителей не участвует. Роль администратора этим скриптом
не выдаётся — см. scripts/grant_role.py.

Использование:
    python -m scripts.add_user "Имя Фамилия" username [--no-queue]
    python -m scripts.add_user "Имя Фамилия" username [--queue-type=long|short]
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

queue_type_arg = None
for arg in list(args):
    if arg.startswith("--queue-type="):
        queue_type_arg = arg.split("=", 1)[1]
        args.remove(arg)

if no_queue and queue_type_arg:
    print("--no-queue и --queue-type нельзя использовать вместе")
    sys.exit(1)

if queue_type_arg and queue_type_arg not in ("long", "short"):
    print(f"--queue-type должен быть long или short (получено: {queue_type_arg!r})")
    sys.exit(1)

if len(args) != 2:
    print(
        'Использование: python -m scripts.add_user "Имя" username '
        "[--no-queue | --queue-type=long|short]"
    )
    sys.exit(1)

name, username = args

with Session(engine) as session:
    existing = session.exec(select(User).where(User.username == username)).first()
    if existing is not None:
        print(f"Пользователь с username={username!r} уже существует (id={existing.id})")
        sys.exit(1)

    user = User(
        name=name,
        username=username,
        is_driver=not no_queue,
        is_dispatcher=no_queue,
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    if no_queue:
        print(f"Добавлен: {user.name} (id={user.id}, username={username}), роль: диспетчер, без очереди")
    else:
        queue_types = [queue_type_arg] if queue_type_arg else ["long", "short"]
        positions = {}
        for qt in queue_types:
            max_position = session.exec(
                select(QueuePosition.position)
                .where(QueuePosition.queue_type == qt)
                .order_by(QueuePosition.position.desc())
            ).first()
            next_position = (max_position or 0) + 1
            session.add(QueuePosition(user_id=user.id, queue_type=qt, position=next_position))
            positions[qt] = next_position
        session.commit()

        positions_text = ", ".join(f"{qt}: позиция {pos}" for qt, pos in positions.items())
        print(f"Добавлен: {user.name} (id={user.id}, username={username}), роль: водитель, {positions_text}")
