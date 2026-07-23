"""Тесты журнала действий (`/activity`) — см. ARCHITECTURE.md,
«Журнал действий». Проверяем, что события пишутся в ожидаемом порядке
и что фильтры на GET /activity работают.
"""
from tests.conftest import seed_queue


def event_types(client, **params):
    return [e["event_type"] for e in client.get("/activity", params=params).json()]


def test_full_order_lifecycle_writes_expected_events(client, db_engine):
    a, b, _ = seed_queue(db_engine, ["A", "B", "C"])

    order_id = client.post("/orders", json={"route": "test", "queue_type": "long"}).json()["id"]
    client.post(f"/orders/{order_id}/respond", json={"user_id": a, "response": "declined"})
    client.post(f"/orders/{order_id}/respond", json={"user_id": b, "response": "accepted"})
    client.post(f"/orders/{order_id}/complete")

    # новые сверху
    assert event_types(client, order_id=order_id) == [
        "order_completed",
        "queue_changed",
        "order_accepted",
        "order_offered",
        "order_declined",
        "order_offered",
        "order_created",
    ]


def test_cancel_assigned_order_logs_queue_change_and_cancellation(client, db_engine):
    a, _, _ = seed_queue(db_engine, ["A", "B", "C"])

    order_id = client.post("/orders", json={"route": "test", "queue_type": "long"}).json()["id"]
    client.post(f"/orders/{order_id}/respond", json={"user_id": a, "response": "accepted"})
    client.post(f"/orders/{order_id}/cancel")

    types = event_types(client, order_id=order_id)
    assert "queue_changed" in types
    assert types[0] == "order_cancelled"


def test_self_assign_logs_reason_and_queue_change(client, db_engine):
    a, b, _ = seed_queue(db_engine, ["A", "B", "C"])

    order_id = client.post("/orders", json={"route": "test", "queue_type": "long"}).json()["id"]
    client.post(
        f"/orders/{order_id}/self-assign",
        json={"user_id": b, "reason": "уже в городе подачи"},
    )

    types = event_types(client, order_id=order_id)
    assert types[0] == "queue_changed"
    assert types[1] == "order_self_assigned"

    self_assign_entry = client.get(
        "/activity", params={"order_id": order_id, "event_type": "order_self_assigned"}
    ).json()[0]
    assert "уже в городе подачи" in self_assign_entry["message"]
    assert self_assign_entry["user_id"] == b


def test_activity_filters_by_event_type_and_user(client, db_engine):
    a, _, _ = seed_queue(db_engine, ["A", "B", "C"])

    client.post("/orders", json={"route": "one", "queue_type": "long"})
    client.post("/orders", json={"route": "two", "queue_type": "long"})

    created_entries = client.get("/activity", params={"event_type": "order_created"}).json()
    assert len(created_entries) == 2

    offered_to_a = client.get("/activity", params={"user_id": a}).json()
    assert all(e["user_id"] == a for e in offered_to_a)
    assert len(offered_to_a) > 0
