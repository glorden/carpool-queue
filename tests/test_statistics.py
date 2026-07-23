"""Тесты статистики (`GET /statistics/summary`) — общие счётчики по
заказам и разбивка по водителям. См. ARCHITECTURE.md, «Статистика».
"""
from sqlmodel import Session

from app.models.user import User
from tests.conftest import seed_queue


def test_overall_counts(client, db_engine):
    a, b, _ = seed_queue(db_engine, ["A", "B", "C"])

    # pending — никому ещё не назначен
    client.post("/orders", json={"route": "pending-1"})

    # assigned — активен, но ещё не завершён
    order2 = client.post("/orders", json={"route": "assigned-1"}).json()
    client.post(f"/orders/{order2['id']}/respond", json={"user_id": a, "response": "accepted"})

    # completed
    order3 = client.post("/orders", json={"route": "completed-1"}).json()
    client.post(f"/orders/{order3['id']}/respond", json={"user_id": b, "response": "accepted"})
    client.post(f"/orders/{order3['id']}/complete")

    # cancelled прямо из pending
    order4 = client.post("/orders", json={"route": "cancelled-1"}).json()
    client.post(f"/orders/{order4['id']}/cancel")

    overall = client.get("/statistics/summary").json()["overall"]

    assert overall["total"] == 4
    assert overall["completed"] == 1
    assert overall["active"] == 2
    assert overall["cancelled"] == 1
    assert overall["total"] == overall["completed"] + overall["active"] + overall["cancelled"]


def test_per_driver_counts_include_self_assign(client, db_engine):
    a, b, c = seed_queue(db_engine, ["A", "B", "C"])

    # A принимает и завершает обычным способом
    order1 = client.post("/orders", json={"route": "one"}).json()
    client.post(f"/orders/{order1['id']}/respond", json={"user_id": a, "response": "accepted"})
    client.post(f"/orders/{order1['id']}/complete")

    # B самоназначается вне очереди и тоже завершает
    order2 = client.post("/orders", json={"route": "two"}).json()
    client.post(f"/orders/{order2['id']}/self-assign", json={"user_id": b, "reason": "рядом"})
    client.post(f"/orders/{order2['id']}/complete")

    by_driver = {d["user_id"]: d for d in client.get("/statistics/summary").json()["by_driver"]}

    assert by_driver[a] == {"user_id": a, "name": "A", "received": 1, "completed": 1, "cancelled": 0}
    assert by_driver[b] == {"user_id": b, "name": "B", "received": 1, "completed": 1, "cancelled": 0}
    assert by_driver[c] == {"user_id": c, "name": "C", "received": 0, "completed": 0, "cancelled": 0}


def test_cancelled_after_assignment_counted_in_received_and_cancelled(client, db_engine):
    a, _, _ = seed_queue(db_engine, ["A", "B", "C"])

    order = client.post("/orders", json={"route": "test"}).json()
    client.post(f"/orders/{order['id']}/respond", json={"user_id": a, "response": "accepted"})
    client.post(f"/orders/{order['id']}/cancel")

    driver_a = next(
        d for d in client.get("/statistics/summary").json()["by_driver"] if d["user_id"] == a
    )

    assert driver_a["received"] == 1
    assert driver_a["cancelled"] == 1
    assert driver_a["completed"] == 0


def test_by_driver_sorted_by_received_descending(client, db_engine):
    a, b, c = seed_queue(db_engine, ["A", "B", "C"])

    for _ in range(2):
        order = client.post("/orders", json={"route": "x"}).json()
        client.post(f"/orders/{order['id']}/self-assign", json={"user_id": c, "reason": "тест"})

    order = client.post("/orders", json={"route": "y"}).json()
    client.post(f"/orders/{order['id']}/self-assign", json={"user_id": a, "reason": "тест"})

    received_order = [d["user_id"] for d in client.get("/statistics/summary").json()["by_driver"]]

    assert received_order == [c, a, b]


def test_by_driver_excludes_users_without_queue_position(client, db_engine):
    seed_queue(db_engine, ["A", "B", "C"])

    with Session(db_engine) as session:
        dispatcher = User(name="Dispatcher", username="dispatcher", password_hash="x")
        session.add(dispatcher)
        session.commit()
        session.refresh(dispatcher)
        dispatcher_id = dispatcher.id

    by_driver = client.get("/statistics/summary").json()["by_driver"]

    assert len(by_driver) == 3
    assert dispatcher_id not in {d["user_id"] for d in by_driver}
