"""Тесты на арифметику позиций в очереди — самое хрупкое место в проекте
(см. ARCHITECTURE.md, «Логика очереди»): принятие, отказ по кругу,
отмена принятого заказа.
"""
from sqlmodel import Session

from app.models.user import User
from tests.conftest import add_to_queue, login_as, queue_order, seed_queue


def test_accept_sends_driver_to_back_of_queue(client, db_engine):
    a, b, c = seed_queue(db_engine, ["A", "B", "C"])

    login_as(db_engine, a)
    order = client.post("/orders", json={"route": "test", "queue_type": "long"}).json()

    resp = client.post(
        f"/orders/{order['id']}/respond",
        json={"response": "accepted"},
    ).json()

    assert resp["status"] == "assigned"
    assert resp["assigned_to"] == a
    assert queue_order(client) == [b, c, a]


def test_decline_offers_to_next_in_ring(client, db_engine):
    a, b, c = seed_queue(db_engine, ["A", "B", "C"])

    login_as(db_engine, a)
    order_id = client.post("/orders", json={"route": "test", "queue_type": "long"}).json()["id"]

    def offered_to():
        return client.get("/orders/pending").json()[0]["offered_to"]["user_id"]

    assert offered_to() == a

    login_as(db_engine, a)
    client.post(f"/orders/{order_id}/respond", json={"response": "declined"})
    assert offered_to() == b

    login_as(db_engine, b)
    client.post(f"/orders/{order_id}/respond", json={"response": "declined"})
    assert offered_to() == c

    # C последний в очереди — отказ должен уйти по кругу обратно к A
    login_as(db_engine, c)
    client.post(f"/orders/{order_id}/respond", json={"response": "declined"})
    assert offered_to() == a

    # отказ никого не двигает в самой очереди
    assert queue_order(client) == [a, b, c]


def test_self_assign_moves_driver_to_back_of_queue(client, db_engine):
    a, b, c = seed_queue(db_engine, ["A", "B", "C"])

    login_as(db_engine, a)
    order = client.post("/orders", json={"route": "test", "queue_type": "long"}).json()

    login_as(db_engine, b)
    resp = client.post(
        f"/orders/{order['id']}/self-assign",
        json={"reason": "уже в городе подачи"},
    )
    body = resp.json()

    assert resp.status_code == 200
    assert body["status"] == "assigned"
    assert body["assigned_to"] == b
    assert body["self_assign_reason"] == "уже в городе подачи"

    # B перепрыгнул очередь и всё равно уходит в конец, как при обычном
    # принятии — существующая логика распределения не меняется
    assert queue_order(client) == [a, c, b]

    # предложение, которое было у A, больше не активно — заказ уже assigned
    assert client.get("/orders/pending").json() == []


def test_self_assign_requires_non_empty_reason(client, db_engine):
    a, _, _ = seed_queue(db_engine, ["A", "B", "C"])
    login_as(db_engine, a)
    order_id = client.post("/orders", json={"route": "test", "queue_type": "long"}).json()["id"]

    resp = client.post(
        f"/orders/{order_id}/self-assign",
        json={"reason": "   "},
    )

    assert resp.status_code == 400


def test_self_assign_rejects_already_assigned_order(client, db_engine):
    a, b, _ = seed_queue(db_engine, ["A", "B", "C"])
    login_as(db_engine, a)
    order_id = client.post("/orders", json={"route": "test", "queue_type": "long"}).json()["id"]

    client.post(f"/orders/{order_id}/respond", json={"response": "accepted"})

    login_as(db_engine, b)
    resp = client.post(
        f"/orders/{order_id}/self-assign",
        json={"reason": "уже рядом"},
    )

    assert resp.status_code == 400


def test_self_assign_rejects_user_outside_queue(client, db_engine):
    a, _, _ = seed_queue(db_engine, ["A", "B", "C"])
    with Session(db_engine) as session:
        dispatcher = User(name="Dispatcher", username="dispatcher", is_dispatcher=True)
        session.add(dispatcher)
        session.commit()
        session.refresh(dispatcher)
        dispatcher_id = dispatcher.id

    login_as(db_engine, a)
    order_id = client.post("/orders", json={"route": "test", "queue_type": "long"}).json()["id"]

    # диспетчер не водитель — require_driver отклоняет раньше, чем дело
    # доходит до проверки принадлежности к конкретной очереди (см.
    # test_roles.py::test_self_assign_rejects_driver_outside_this_queue_type
    # для сценария "водитель есть, но не в этой очереди")
    login_as(db_engine, dispatcher_id)
    resp = client.post(
        f"/orders/{order_id}/self-assign",
        json={"reason": "уже рядом"},
    )

    assert resp.status_code == 403


def test_cancel_assigned_order_returns_driver_to_second_place(client, db_engine):
    a, b, c = seed_queue(db_engine, ["A", "B", "C"])

    login_as(db_engine, a)
    order1_id = client.post("/orders", json={"route": "order1", "queue_type": "long"}).json()["id"]
    client.post(
        f"/orders/{order1_id}/respond",
        json={"response": "accepted"},
    )
    assert queue_order(client) == [b, c, a]

    # второй заказ уходит текущему первому (B)
    login_as(db_engine, a)
    client.post("/orders", json={"route": "order2", "queue_type": "long"})
    assert client.get("/orders/pending").json()[0]["offered_to"]["user_id"] == b

    cancelled = client.post(f"/orders/{order1_id}/cancel").json()
    assert cancelled["status"] == "cancelled"

    # A возвращается вторым, сразу после текущего первого (B), не обгоняя его
    assert queue_order(client) == [b, a, c]


# --- Независимость двух очередей (long/short) ---
# Один и тот же состав людей специально сажается в short в ДРУГОМ порядке,
# чем в long (через add_to_queue) — если фильтр по queue_type где-то
# пропущен, эти тесты это обнаружат.


def test_accept_in_short_queue_does_not_touch_long_queue(client, db_engine):
    a, b, c = seed_queue(db_engine, ["A", "B", "C"])  # long: a, b, c
    add_to_queue(db_engine, [c, a, b], "short")

    login_as(db_engine, c)
    order = client.post("/orders", json={"route": "test", "queue_type": "short"}).json()
    client.post(f"/orders/{order['id']}/respond", json={"response": "accepted"})

    assert queue_order(client, "short") == [a, b, c]  # c ушёл в конец short
    assert queue_order(client, "long") == [a, b, c]  # long не тронут вовсе


def test_decline_wraps_within_short_queue_only(client, db_engine):
    a, b, c = seed_queue(db_engine, ["A", "B", "C"])
    add_to_queue(db_engine, [a, b, c], "short")

    login_as(db_engine, a)
    order_id = client.post("/orders", json={"route": "t", "queue_type": "short"}).json()["id"]

    def offered_to():
        return client.get("/orders/pending").json()[0]["offered_to"]["user_id"]

    login_as(db_engine, a)
    client.post(f"/orders/{order_id}/respond", json={"response": "declined"})
    login_as(db_engine, b)
    client.post(f"/orders/{order_id}/respond", json={"response": "declined"})
    login_as(db_engine, c)
    client.post(f"/orders/{order_id}/respond", json={"response": "declined"})
    assert offered_to() == a  # по кругу внутри short

    assert queue_order(client, "long") == [a, b, c]  # long вообще не задет


def test_self_assign_in_one_queue_does_not_move_other_queue(client, db_engine):
    a, b, c = seed_queue(db_engine, ["A", "B", "C"])
    add_to_queue(db_engine, [a, b, c], "short")

    login_as(db_engine, a)
    order = client.post("/orders", json={"route": "t", "queue_type": "short"}).json()

    login_as(db_engine, b)
    client.post(
        f"/orders/{order['id']}/self-assign",
        json={"reason": "рядом"},
    )

    assert queue_order(client, "short") == [a, c, b]
    assert queue_order(client, "long") == [a, b, c]


def test_cancel_in_short_queue_does_not_reindex_long_queue(client, db_engine):
    a, b, c = seed_queue(db_engine, ["A", "B", "C"])
    add_to_queue(db_engine, [a, b, c], "short")

    login_as(db_engine, a)
    order = client.post("/orders", json={"route": "t", "queue_type": "short"}).json()
    client.post(f"/orders/{order['id']}/respond", json={"response": "accepted"})
    client.post(f"/orders/{order['id']}/cancel")

    assert queue_order(client, "short") == [b, a, c]  # a вернулся вторым в short
    assert queue_order(client, "long") == [a, b, c]  # long не переиндексирован


def test_create_order_offers_only_within_its_own_queue_type(client, db_engine):
    a, b, c = seed_queue(db_engine, ["A", "B", "C"])  # long: a, b, c
    add_to_queue(db_engine, [c, b, a], "short")  # намеренно другой первый

    login_as(db_engine, a)
    client.post("/orders", json={"route": "t", "queue_type": "short"})
    offered = client.get("/orders/pending").json()[0]["offered_to"]["user_id"]
    assert offered == c  # первый в short, не первый в long


def test_create_order_requires_explicit_queue_type(client, db_engine):
    a, _, _ = seed_queue(db_engine, ["A", "B", "C"])
    login_as(db_engine, a)

    resp = client.post("/orders", json={"route": "t"})  # без queue_type

    assert resp.status_code == 422
