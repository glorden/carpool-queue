"""Общие фикстуры для тестов: изолированная SQLite-БД на тест + TestClient.

Каждый тест получает свою временную БД (через tmp_path) — тесты не
трогают carpool.db и не зависят друг от друга.
"""
import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine

from app.auth import get_current_user_optional, get_current_user_required
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
    # base_url на https — иначе Secure-cookie сессии (SESSION_COOKIE_SECURE,
    # см. app/main.py) не возвращался бы обратно на дефолтном http://testserver,
    # и вход через VK нельзя было бы протестировать (см. ARCHITECTURE.md,
    # «Вход через VK ID»). На проде трафик снаружи всегда HTTPS (Caddy).
    with TestClient(app, base_url="https://testserver") as test_client:
        yield test_client
    app.dependency_overrides.clear()


def login_as(engine, user_id):
    """Переопределяет текущего пользователя сессии для последующих запросов
    через client — тест действует от имени user_id без реального похода
    в VK (см. ARCHITECTURE.md, «Технический долг», Шаг 26)."""

    def _load():
        with Session(engine) as session:
            return session.get(User, user_id)

    app.dependency_overrides[get_current_user_required] = _load
    app.dependency_overrides[get_current_user_optional] = _load


def logout_test_client():
    """Убирает переопределение, поставленное login_as() — дальше
    current_user снова читается из настоящей cookie-сессии (пустой,
    т.к. login_as её не трогает). Не путать с эндпоинтом POST /auth/logout
    (тот чистит cookie-сессию, но не dependency_overrides)."""
    app.dependency_overrides.pop(get_current_user_required, None)
    app.dependency_overrides.pop(get_current_user_optional, None)


def seed_queue(engine, names, queue_type="long"):
    """Создаёт пользователей и ставит их в очередь заданного типа
    (по умолчанию long) в переданном порядке.

    Возвращает список user_id в том же порядке.
    """
    ids = []
    with Session(engine) as session:
        for name in names:
            user = User(name=name, username=name.lower())
            session.add(user)
            session.commit()
            session.refresh(user)
            ids.append(user.id)

        for position, user_id in enumerate(ids):
            session.add(
                QueuePosition(user_id=user_id, queue_type=queue_type, position=position)
            )
        session.commit()

    return ids


def add_to_queue(engine, user_ids, queue_type):
    """Добавляет уже существующих пользователей в очередь заданного типа,
    в переданном порядке — без создания новых User (в отличие от
    seed_queue). Нужен для сценариев, где один и тот же состав людей
    должен независимо состоять в обеих очередях.
    """
    with Session(engine) as session:
        for position, user_id in enumerate(user_ids):
            session.add(
                QueuePosition(user_id=user_id, queue_type=queue_type, position=position)
            )
        session.commit()


def queue_order(client, queue_type="long"):
    """Список user_id в текущем порядке очереди заданного типа (по GET /queue)."""
    return [
        entry["user_id"]
        for entry in client.get(f"/queue?queue_type={queue_type}").json()
    ]
