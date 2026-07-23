"""Тесты на арифметику позиций в очереди — самое хрупкое место в проекте
(см. ARCHITECTURE.md, «Логика очереди»): принятие, отказ по кругу,
отмена принятого заказа.
"""
from tests.conftest import add_to_queue, queue_order, seed_queue


def test_accept_sends_driver_to_back_of_queue(client, db_engine):
    a, b, c = seed_queue(db_engine, ["A", "B", "C"])

    order = client.post("/orders", json={"route": "test", "queue_type": "long"}).json()

    resp = client.post(
        f"/orders/{order['id']}/respond",
        json={"user_id": a, "response": "accepted"},
    ).json()

    assert resp["status"] == "assigned"
    assert resp["assigned_to"] == a
    assert queue_order(client) == [b, c, a]


def test_decline_offers_to_next_in_ring(client, db_engine):
    a, b, c = seed_queue(db_engine, ["A", "B", "C"])

    order_id = client.post("/orders", json={"route": "test", "queue_type": "long"}).json()["id"]

    def offered_to():
        return client.get("/orders/pending").json()[0]["offered_to"]["user_id"]

    assert offered_to() == a

    client.post(f"/orders/{order_id}/respond", json={"user_id": a, "response": "declined"})
    assert offered_to() == b

    client.post(f"/orders/{order_id}/respond", json={"user_id": b, "response": "declined"})
    assert offered_to() == c

    # C последний в очереди — отказ должен уйти по кругу обратно к A
    client.post(f"/orders/{order_id}/respond", json={"user_id": c, "response": "declined"})
    assert offered_to() == a

    # отказ никого не двигает в самой очереди
    assert queue_order(client) == [a, b, c]


def test_self_assign_moves_driver_to_back_of_queue(client, db_engine):
    a, b, c = seed_queue(db_engine, ["A", "B", "C"])

    order = client.post("/orders", json={"route": "test", "queue_type": "long"}).json()

    resp = client.post(
        f"/orders/{order['id']}/self-assign",
        json={"user_id": b, "reason": "уже в городе подачи"},
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
    seed_queue(db_engine, ["A", "B", "C"])
    order_id = client.post("/orders", json={"route": "test", "queue_type": "long"}).json()["id"]

    resp = client.post(
        f"/orders/{order_id}/self-assign",
        json={"user_id": 1, "reason": "   "},
    )

    assert resp.status_code == 400


def test_self_assign_rejects_already_assigned_order(client, db_engine):
    a, b, _ = seed_queue(db_engine, ["A", "B", "C"])
    order_id = client.post("/orders", json={"route": "test", "queue_type": "long"}).json()["id"]

    client.post(f"/orders/{order_id}/respond", json={"user_id": a, "response": "accepted"})

    resp = client.post(
        f"/orders/{order_id}/self-assign",
        json={"user_id": b, "reason": "уже рядом"},
    )

    assert resp.status_code == 400


def test_self_assign_rejects_user_outside_queue(client, db_engine):
    seed_queue(db_engine, ["A", "B", "C"])
    order_id = client.post("/orders", json={"route": "test", "queue_type": "long"}).json()["id"]

    resp = client.post(
        f"/orders/{order_id}/self-assign",
        json={"user_id": 9999, "reason": "уже рядом"},
    )

    assert resp.status_code == 400


def test_cancel_assigned_order_returns_driver_to_second_place(client, db_engine):
    a, b, c = seed_queue(db_engine, ["A", "B", "C"])

    order1_id = client.post("/orders", json={"route": "order1", "queue_type": "long"}).json()["id"]
    client.post(
        f"/orders/{order1_id}/respond",
        json={"user_id": a, "response": "accepted"},
    )
    assert queue_order(client) == [b, c, a]

    # второй заказ уходит текущему первому (B)
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

    order = client.post("/orders", json={"route": "test", "queue_type": "short"}).json()
    client.post(f"/orders/{order['id']}/respond", json={"user_id": c, "response": "accepted"})

    assert queue_order(client, "short") == [a, b, c]  # c ушёл в конец short
    assert queue_order(client, "long") == [a, b, c]  # long не тронут вовсе


def test_decline_wraps_within_short_queue_only(client, db_engine):
    a, b, c = seed_queue(db_engine, ["A", "B", "C"])
    add_to_queue(db_engine, [a, b, c], "short")

    order_id = client.post("/orders", json={"route": "t", "queue_type": "short"}).json()["id"]

    def offered_to():
        return client.get("/orders/pending").json()[0]["offered_to"]["user_id"]

    client.post(f"/orders/{order_id}/respond", json={"user_id": a, "response": "declined"})
    client.post(f"/orders/{order_id}/respond", json={"user_id": b, "response": "declined"})
    client.post(f"/orders/{order_id}/respond", json={"user_id": c, "response": "declined"})
    assert offered_to() == a  # по кругу внутри short

    assert queue_order(client, "long") == [a, b, c]  # long вообще не задет


def test_self_assign_in_one_queue_does_not_move_other_queue(client, db_engine):
    a, b, c = seed_queue(db_engine, ["A", "B", "C"])
    add_to_queue(db_engine, [a, b, c], "short")

    order = client.post("/orders", json={"route": "t", "queue_type": "short"}).json()
    client.post(
        f"/orders/{order['id']}/self-assign",
        json={"user_id": b, "reason": "рядом"},
    )

    assert queue_order(client, "short") == [a, c, b]
    assert queue_order(client, "long") == [a, b, c]


def test_cancel_in_short_queue_does_not_reindex_long_queue(client, db_engine):
    a, b, c = seed_queue(db_engine, ["A", "B", "C"])
    add_to_queue(db_engine, [a, b, c], "short")

    order = client.post("/orders", json={"route": "t", "queue_type": "short"}).json()
    client.post(f"/orders/{order['id']}/respond", json={"user_id": a, "response": "accepted"})
    client.post(f"/orders/{order['id']}/cancel")

    assert queue_order(client, "short") == [b, a, c]  # a вернулся вторым в short
    assert queue_order(client, "long") == [a, b, c]  # long не переиндексирован


def test_create_order_offers_only_within_its_own_queue_type(client, db_engine):
    a, b, c = seed_queue(db_engine, ["A", "B", "C"])  # long: a, b, c
    add_to_queue(db_engine, [c, b, a], "short")  # намеренно другой первый

    client.post("/orders", json={"route": "t", "queue_type": "short"})
    offered = client.get("/orders/pending").json()[0]["offered_to"]["user_id"]
    assert offered == c  # первый в short, не первый в long


def test_create_order_requires_explicit_queue_type(client, db_engine):
    seed_queue(db_engine, ["A", "B", "C"])

    resp = client.post("/orders", json={"route": "t"})  # без queue_type

    assert resp.status_code == 422
