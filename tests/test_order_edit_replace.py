"""Тесты редактирования и замены заказа (PATCH /orders/{id},
POST /orders/{id}/replace) — см. ARCHITECTURE.md, «Редактирование и
замена заказа» (Шаг 32). Ролевые 403/200-проверки — в test_roles.py,
здесь — поведение самой механики.
"""
from sqlmodel import Session

from app.models.user import User
from tests.conftest import login_as, queue_order, seed_queue


def _make_user(engine, name, **roles):
    with Session(engine) as session:
        user = User(name=name, username=name.lower(), **roles)
        session.add(user)
        session.commit()
        session.refresh(user)
        return user.id


# --- PATCH /orders/{id} ---


def test_edit_updates_route_and_comment(client, db_engine):
    a, _, _ = seed_queue(db_engine, ["A", "B", "C"])
    login_as(db_engine, a)
    order_id = client.post(
        "/orders", json={"route": "old", "comment": "c1", "queue_type": "long"}
    ).json()["id"]

    dispatcher_id = _make_user(db_engine, "Dispatcher", is_dispatcher=True)
    login_as(db_engine, dispatcher_id)
    resp = client.patch(f"/orders/{order_id}", json={"route": "new", "comment": "c2"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["route"] == "new"
    assert body["comment"] == "c2"
    assert body["queue_type"] == "long"  # не тронут


def test_edit_partial_keeps_other_field(client, db_engine):
    a, _, _ = seed_queue(db_engine, ["A", "B", "C"])
    login_as(db_engine, a)
    order_id = client.post(
        "/orders", json={"route": "old", "comment": "keep-me", "queue_type": "long"}
    ).json()["id"]

    dispatcher_id = _make_user(db_engine, "Dispatcher", is_dispatcher=True)
    login_as(db_engine, dispatcher_id)
    resp = client.patch(f"/orders/{order_id}", json={"route": "new"})

    assert resp.json()["comment"] == "keep-me"


def test_edit_empty_string_clears_field(client, db_engine):
    a, _, _ = seed_queue(db_engine, ["A", "B", "C"])
    login_as(db_engine, a)
    order_id = client.post(
        "/orders", json={"route": "old", "comment": "c1", "queue_type": "long"}
    ).json()["id"]

    dispatcher_id = _make_user(db_engine, "Dispatcher", is_dispatcher=True)
    login_as(db_engine, dispatcher_id)
    resp = client.patch(f"/orders/{order_id}", json={"comment": ""})

    assert resp.json()["comment"] == ""


def test_edit_empty_body_is_noop_and_not_logged(client, db_engine):
    a, _, _ = seed_queue(db_engine, ["A", "B", "C"])
    login_as(db_engine, a)
    order_id = client.post(
        "/orders", json={"route": "old", "comment": "c1", "queue_type": "long"}
    ).json()["id"]

    dispatcher_id = _make_user(db_engine, "Dispatcher", is_dispatcher=True)
    login_as(db_engine, dispatcher_id)
    resp = client.patch(f"/orders/{order_id}", json={})

    assert resp.status_code == 200
    assert resp.json()["route"] == "old"

    types = [e["event_type"] for e in client.get("/activity", params={"order_id": order_id}).json()]
    assert "order_edited" not in types


def test_edit_rejects_completed_order(client, db_engine):
    a, _, _ = seed_queue(db_engine, ["A", "B", "C"])
    login_as(db_engine, a)
    order_id = client.post("/orders", json={"route": "t", "queue_type": "long"}).json()["id"]
    client.post(f"/orders/{order_id}/respond", json={"response": "accepted"})
    client.post(f"/orders/{order_id}/complete")

    dispatcher_id = _make_user(db_engine, "Dispatcher", is_dispatcher=True)
    login_as(db_engine, dispatcher_id)
    resp = client.patch(f"/orders/{order_id}", json={"comment": "поздно"})
    assert resp.status_code == 400


def test_edit_rejects_cancelled_order(client, db_engine):
    a, _, _ = seed_queue(db_engine, ["A", "B", "C"])
    login_as(db_engine, a)
    order_id = client.post("/orders", json={"route": "t", "queue_type": "long"}).json()["id"]
    client.post(f"/orders/{order_id}/cancel")

    dispatcher_id = _make_user(db_engine, "Dispatcher", is_dispatcher=True)
    login_as(db_engine, dispatcher_id)
    resp = client.patch(f"/orders/{order_id}", json={"comment": "поздно"})
    assert resp.status_code == 400


def test_edit_logs_diff_message_only_for_changed_fields(client, db_engine):
    a, _, _ = seed_queue(db_engine, ["A", "B", "C"])
    login_as(db_engine, a)
    order_id = client.post(
        "/orders", json={"route": "old", "comment": "c1", "queue_type": "long"}
    ).json()["id"]

    dispatcher_id = _make_user(db_engine, "Dispatcher", is_dispatcher=True)
    login_as(db_engine, dispatcher_id)
    client.patch(f"/orders/{order_id}", json={"route": "new"})

    entries = client.get(
        "/activity", params={"order_id": order_id, "event_type": "order_edited"}
    ).json()
    assert len(entries) == 1
    assert "маршрут" in entries[0]["message"]
    assert "комментарий" not in entries[0]["message"]  # comment не менялся
    assert entries[0]["user_id"] == dispatcher_id


# --- POST /orders/{id}/replace ---


def test_replace_pending_order_sets_replaces_order_id(client, db_engine):
    a, _, _ = seed_queue(db_engine, ["A", "B", "C"])
    login_as(db_engine, a)
    order_id = client.post("/orders", json={"route": "old", "queue_type": "long"}).json()["id"]

    dispatcher_id = _make_user(db_engine, "Dispatcher", is_dispatcher=True)
    login_as(db_engine, dispatcher_id)
    resp = client.post(f"/orders/{order_id}/replace", json={"route": "new", "queue_type": "short"})

    assert resp.status_code == 200
    new_order = resp.json()
    assert new_order["replaces_order_id"] == order_id
    assert new_order["queue_type"] == "short"
    assert new_order["status"] == "pending"

    old_order = next(o for o in client.get("/orders").json() if o["id"] == order_id)
    assert old_order["status"] == "cancelled"


def test_replace_assigned_order_requeues_like_cancel(client, db_engine):
    a, b, c = seed_queue(db_engine, ["A", "B", "C"])
    login_as(db_engine, a)
    order_id = client.post("/orders", json={"route": "t", "queue_type": "long"}).json()["id"]
    client.post(f"/orders/{order_id}/respond", json={"response": "accepted"})
    assert queue_order(client) == [b, c, a]  # a принял -> ушёл в конец

    dispatcher_id = _make_user(db_engine, "Dispatcher", is_dispatcher=True)
    login_as(db_engine, dispatcher_id)
    resp = client.post(f"/orders/{order_id}/replace", json={"route": "new", "queue_type": "long"})

    assert resp.status_code == 200
    # a (был исполнителем старого) возвращается вторым — та же логика, что у /cancel
    assert queue_order(client) == [b, a, c]
    assert client.get("/orders/pending").json()[0]["offered_to"]["user_id"] == b


def test_replace_rejects_completed_order(client, db_engine):
    a, _, _ = seed_queue(db_engine, ["A", "B", "C"])
    login_as(db_engine, a)
    order_id = client.post("/orders", json={"route": "t", "queue_type": "long"}).json()["id"]
    client.post(f"/orders/{order_id}/respond", json={"response": "accepted"})
    client.post(f"/orders/{order_id}/complete")

    dispatcher_id = _make_user(db_engine, "Dispatcher", is_dispatcher=True)
    login_as(db_engine, dispatcher_id)
    resp = client.post(f"/orders/{order_id}/replace", json={"route": "new", "queue_type": "long"})
    assert resp.status_code == 400


def test_replace_rejects_cancelled_order(client, db_engine):
    a, _, _ = seed_queue(db_engine, ["A", "B", "C"])
    login_as(db_engine, a)
    order_id = client.post("/orders", json={"route": "t", "queue_type": "long"}).json()["id"]
    client.post(f"/orders/{order_id}/cancel")

    dispatcher_id = _make_user(db_engine, "Dispatcher", is_dispatcher=True)
    login_as(db_engine, dispatcher_id)
    resp = client.post(f"/orders/{order_id}/replace", json={"route": "new", "queue_type": "long"})
    assert resp.status_code == 400


def test_replace_activity_log_sequence(client, db_engine):
    a, b, _ = seed_queue(db_engine, ["A", "B", "C"])
    login_as(db_engine, a)
    order_id = client.post("/orders", json={"route": "t", "queue_type": "long"}).json()["id"]

    dispatcher_id = _make_user(db_engine, "Dispatcher", is_dispatcher=True)
    login_as(db_engine, dispatcher_id)
    new_order_id = client.post(
        f"/orders/{order_id}/replace", json={"route": "new", "queue_type": "long"}
    ).json()["id"]

    old_types = [e["event_type"] for e in client.get("/activity", params={"order_id": order_id}).json()]
    assert old_types == ["order_replaced", "order_cancelled", "order_offered", "order_created"]

    new_types = [
        e["event_type"] for e in client.get("/activity", params={"order_id": new_order_id}).json()
    ]
    assert new_types == ["order_replaced", "order_offered", "order_created"]
