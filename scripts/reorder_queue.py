"""Переставляет очередь водителей в указанном порядке.

Список username должен содержать ровно тех же людей, что сейчас состоят
в очереди — без пропусков и без лишних, чтобы не потерять или не
задвоить кого-то по ошибке.

Использование:
    python -m scripts.reorder_queue username1 username2 username3 ...
"""
import sys

from sqlmodel import Session, select

from app.database import engine
from app.models.queue import QueuePosition
from app.models.user import User

usernames = sys.argv[1:]

if not usernames:
    print("Использование: python -m scripts.reorder_queue username1 username2 ...")
    sys.exit(1)

if len(usernames) != len(set(usernames)):
    print("В списке есть повторяющиеся username")
    sys.exit(1)

with Session(engine) as session:
    users_by_username = {}
    missing_usernames = []
    for username in usernames:
        user = session.exec(select(User).where(User.username == username)).first()
        if user is None:
            missing_usernames.append(username)
        else:
            users_by_username[username] = user

    if missing_usernames:
        print(f"Пользователи не найдены: {', '.join(missing_usernames)}")
        sys.exit(1)

    current_qps = session.exec(select(QueuePosition)).all()
    qp_by_user_id = {qp.user_id: qp for qp in current_qps}
    current_user_ids = set(qp_by_user_id.keys())
    new_user_ids = {user.id for user in users_by_username.values()}

    if current_user_ids != new_user_ids:
        missing_from_list = current_user_ids - new_user_ids
        extra_in_list = new_user_ids - current_user_ids

        if missing_from_list:
            names = [
                user.name
                for user in session.exec(select(User))
                if user.id in missing_from_list
            ]
            print(f"В списке не хватает тех, кто сейчас в очереди: {', '.join(names)}")

        if extra_in_list:
            names = [
                user.name
                for user in users_by_username.values()
                if user.id in extra_in_list
            ]
            print(f"В списке есть те, кого сейчас нет в очереди: {', '.join(names)}")

        sys.exit(1)

    for position, username in enumerate(usernames):
        user = users_by_username[username]
        qp_by_user_id[user.id].position = position
        session.add(qp_by_user_id[user.id])

    session.commit()

    print("Новый порядок очереди:")
    for position, username in enumerate(usernames):
        user = users_by_username[username]
        print(f"  {position + 1}. {user.name} ({username})")
