"""Общие фикстуры для тестов: изолированная SQLite-БД на тест + TestClient.

Каждый тест получает свою временную БД (через tmp_path) — тесты не
трогают carpool.db и не зависят друг от друга.
"""
import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine

from app.database import get_session
from app.main import app
from app.models.queue import QueuePosition
from app.models.user import User


@pytest.fixture()
def db_engine(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture()
def client(db_engine):
    def override_get_session():
        with Session(db_engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def seed_queue(engine, names):
    """Создаёт пользователей и ставит их в очередь в переданном порядке.

    Возвращает список user_id в том же порядке.
    """
    ids = []
    with Session(engine) as session:
        for name in names:
            user = User(name=name, username=name.lower(), password_hash="x")
            session.add(user)
            session.commit()
            session.refresh(user)
            ids.append(user.id)

        for position, user_id in enumerate(ids):
            session.add(QueuePosition(user_id=user_id, position=position))
        session.commit()

    return ids


def queue_order(client):
    """Список user_id в текущем порядке очереди (по GET /queue)."""
    return [entry["user_id"] for entry in client.get("/queue").json()]
