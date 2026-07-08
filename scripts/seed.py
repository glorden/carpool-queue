"""Скрипт для наполнения БД тестовыми данными (для проверки /queue вручную)."""
from sqlmodel import Session
from app.database import engine
from app.models.user import User
from app.models.queue import QueuePosition

with Session(engine) as session:
    user1 = User(name="Иван", username="ivan", password_hash="test")
    user2 = User(name="Мария", username="maria", password_hash="test")
    session.add(user1)
    session.add(user2)
    session.commit()
    session.refresh(user1)
    session.refresh(user2)

    session.add(QueuePosition(user_id=user1.id, position=1))
    session.add(QueuePosition(user_id=user2.id, position=2))
    session.commit()

    print("Тестовые данные добавлены:")
    print(f"  {user1.name} — позиция 1")
    print(f"  {user2.name} — позиция 2")