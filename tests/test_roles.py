"""Тесты ролевой модели (см. ARCHITECTURE.md, «Роли и права доступа») —
is_driver/is_dispatcher/is_admin, прямое назначение диспетчером (/assign),
расширенные права на /cancel, admin-only /admin/* эндпоинты.
"""
from sqlmodel import Session

from app.models.order import OrderOffer
from app.models.queue import QueuePosition, QueueType
from app.models.user import User
from tests.conftest import login_as, queue_order, seed_queue


def _make_user(engine, name, **roles):
    with Session(engine) as session:
        user = User(name=name, username=name.lower(), **roles)
        session.add(user)
        session.commit()
        session.refresh(user)
        return user.id


# --- require_driver: self-assign/respond/complete ---


def test_self_assign_requires_driver_role(client, db_engine):
    a, _, _ = seed_queue(db_engine, ["A", "B", "C"])
    login_as(db_engine, a)
    order_id = client.post("/orders", json={"route": "t", "queue_type": "long"}).json()["id"]

    dispatcher_id = _make_user(db_engine, "Dispatcher", is_dispatcher=True)
    login_as(db_engine, dispatcher_id)
    resp = client.post(f"/orders/{order_id}/self-assign", json={"reason": "рядом"})
    assert resp.status_code == 403


def test_self_assign_rejects_driver_outside_this_queue_type(client, db_engine):
    """Роль есть, но в этой конкретной очереди водителя нет — бизнес-правило
    даёт 400, отдельно от ролевого гейта (см. test_queue_logic.py — тот же
    сценарий без роли даёт 403 раньше, до этой проверки)."""
    a, _, _ = seed_queue(db_engine, ["A", "B", "C"])
    login_as(db_engine, a)
    order_id = client.post("/orders", json={"route": "t", "queue_type": "long"}).json()["id"]

    driver_id = _make_user(db_engine, "OnlyShort", is_driver=True)
    with Session(db_engine) as session:
        session.add(QueuePosition(user_id=driver_id, queue_type=QueueType.short, position=0))
        session.commit()

    login_as(db_engine, driver_id)
    resp = client.post(f"/orders/{order_id}/self-assign", json={"reason": "рядом"})
    assert resp.status_code == 400


def test_respond_requires_driver_role(client, db_engine):
    a, _, _ = seed_queue(db_engine, ["A", "B", "C"])
    login_as(db_engine, a)
    order_id = client.post("/orders", json={"route": "t", "queue_type": "long"}).json()["id"]

    non_driver_id = _make_user(db_engine, "NonDriver")
    with Session(db_engine) as session:
        session.add(OrderOffer(order_id=order_id, user_id=non_driver_id))
        session.commit()

    login_as(db_engine, non_driver_id)
    resp = client.post(f"/orders/{order_id}/respond", json={"response": "accepted"})
    assert resp.status_code == 403


def test_complete_requires_driver_role(client, db_engine):
    a, _, _ = seed_queue(db_engine, ["A", "B", "C"])
    login_as(db_engine, a)
    order_id = client.post("/orders", json={"route": "t", "queue_type": "long"}).json()["id"]
    client.post(f"/orders/{order_id}/respond", json={"response": "accepted"})

    # роль снята "задним числом" (например, через /admin) уже после того,
    # как заказ назначен — require_driver должен сработать и здесь
    with Session(db_engine) as session:
        user = session.get(User, a)
        user.is_driver = False
        session.add(user)
        session.commit()

    resp = client.post(f"/orders/{order_id}/complete")
    assert resp.status_code == 403


# --- is_admin проходит любую ролевую проверку ---


def test_admin_passes_driver_gate_without_driver_role(client, db_engine):
    a, _, _ = seed_queue(db_engine, ["A", "B", "C"])
    login_as(db_engine, a)
    order_id = client.post("/orders", json={"route": "t", "queue_type": "long"}).json()["id"]

    admin_id = _make_user(db_engine, "Admin", is_admin=True)
    with Session(db_engine) as session:
        session.add(QueuePosition(user_id=admin_id, queue_type=QueueType.long, position=99))
        session.commit()

    login_as(db_engine, admin_id)
    resp = client.post(f"/orders/{order_id}/self-assign", json={"reason": "рядом"})
    assert resp.status_code == 200


# --- /cancel: dispatcher/admin могут отменить любой заказ ---


def test_dispatcher_can_cancel_any_order(client, db_engine):
    a, b, _ = seed_queue(db_engine, ["A", "B", "C"])
    login_as(db_engine, b)  # создатель — b
    order_id = client.post("/orders", json={"route": "t", "queue_type": "long"}).json()["id"]
    login_as(db_engine, a)  # исполнитель — a
    client.post(f"/orders/{order_id}/respond", json={"response": "accepted"})

    dispatcher_id = _make_user(db_engine, "Dispatcher", is_dispatcher=True)
    login_as(db_engine, dispatcher_id)  # ни создатель, ни исполнитель
    resp = client.post(f"/orders/{order_id}/cancel")
    assert resp.status_code == 200


def test_admin_can_cancel_any_order(client, db_engine):
    a, b, _ = seed_queue(db_engine, ["A", "B", "C"])
    login_as(db_engine, b)
    order_id = client.post("/orders", json={"route": "t", "queue_type": "long"}).json()["id"]

    admin_id = _make_user(db_engine, "Admin", is_admin=True)
    login_as(db_engine, admin_id)
    resp = client.post(f"/orders/{order_id}/cancel")
    assert resp.status_code == 200


# --- POST /orders/{id}/assign ---


def test_assign_requires_dispatcher_role(client, db_engine):
    a, _, _ = seed_queue(db_engine, ["A", "B", "C"])
    login_as(db_engine, a)
    order_id = client.post("/orders", json={"route": "t", "queue_type": "long"}).json()["id"]

    resp = client.post(f"/orders/{order_id}/assign", json={"driver_user_id": a})
    assert resp.status_code == 403  # a — водитель, не диспетчер


def test_assign_rejects_non_driver_target(client, db_engine):
    a, _, _ = seed_queue(db_engine, ["A", "B", "C"])
    login_as(db_engine, a)
    order_id = client.post("/orders", json={"route": "t", "queue_type": "long"}).json()["id"]

    dispatcher_id = _make_user(db_engine, "Dispatcher", is_dispatcher=True)
    login_as(db_engine, dispatcher_id)
    resp = client.post(f"/orders/{order_id}/assign", json={"driver_user_id": dispatcher_id})
    assert resp.status_code == 400


def test_assign_rejects_driver_outside_this_queue_type(client, db_engine):
    a, _, _ = seed_queue(db_engine, ["A", "B", "C"])
    login_as(db_engine, a)
    order_id = client.post("/orders", json={"route": "t", "queue_type": "long"}).json()["id"]

    driver_id = _make_user(db_engine, "OnlyShort", is_driver=True)
    with Session(db_engine) as session:
        session.add(QueuePosition(user_id=driver_id, queue_type=QueueType.short, position=0))
        session.commit()

    dispatcher_id = _make_user(db_engine, "Dispatcher", is_dispatcher=True)
    login_as(db_engine, dispatcher_id)
    resp = client.post(f"/orders/{order_id}/assign", json={"driver_user_id": driver_id})
    assert resp.status_code == 400


def test_dispatcher_assign_pending_order_to_driver(client, db_engine):
    a, b, c = seed_queue(db_engine, ["A", "B", "C"])
    login_as(db_engine, a)
    order_id = client.post("/orders", json={"route": "t", "queue_type": "long"}).json()["id"]
    # оффер сейчас у a (первый в очереди)

    dispatcher_id = _make_user(db_engine, "Dispatcher", is_dispatcher=True)
    login_as(db_engine, dispatcher_id)
    resp = client.post(f"/orders/{order_id}/assign", json={"driver_user_id": c})

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "assigned"
    assert body["assigned_to"] == c
    assert queue_order(client) == [a, b, c]  # c уходит в конец, a/b не тронуты

    # старый оффер a теперь неактивен (declined диспетчером при назначении)
    login_as(db_engine, a)
    resp2 = client.post(f"/orders/{order_id}/respond", json={"response": "accepted"})
    assert resp2.status_code == 403


def test_dispatcher_reassign_returns_previous_driver_second_and_moves_new_driver_last(
    client, db_engine
):
    a, b, c = seed_queue(db_engine, ["A", "B", "C"])
    login_as(db_engine, a)
    order_id = client.post("/orders", json={"route": "t", "queue_type": "long"}).json()["id"]
    client.post(f"/orders/{order_id}/respond", json={"response": "accepted"})
    assert queue_order(client) == [b, c, a]  # a принял -> ушёл в конец

    dispatcher_id = _make_user(db_engine, "Dispatcher", is_dispatcher=True)
    login_as(db_engine, dispatcher_id)
    resp = client.post(f"/orders/{order_id}/assign", json={"driver_user_id": b})

    assert resp.status_code == 200
    assert resp.json()["assigned_to"] == b
    # a (прежний исполнитель) — второй, не обгоняя того, кто был первым (b);
    # b (новый исполнитель) сразу уходит в конец, как при обычном принятии
    assert queue_order(client) == [a, c, b]


def test_assign_already_assigned_to_same_driver_rejected(client, db_engine):
    a, _, _ = seed_queue(db_engine, ["A", "B", "C"])
    login_as(db_engine, a)
    order_id = client.post("/orders", json={"route": "t", "queue_type": "long"}).json()["id"]
    client.post(f"/orders/{order_id}/respond", json={"response": "accepted"})

    dispatcher_id = _make_user(db_engine, "Dispatcher", is_dispatcher=True)
    login_as(db_engine, dispatcher_id)
    resp = client.post(f"/orders/{order_id}/assign", json={"driver_user_id": a})
    assert resp.status_code == 400


# --- PATCH /orders/{id} ---


def test_update_order_requires_dispatcher_role(client, db_engine):
    a, _, _ = seed_queue(db_engine, ["A", "B", "C"])
    login_as(db_engine, a)
    order_id = client.post("/orders", json={"route": "t", "queue_type": "long"}).json()["id"]

    resp = client.patch(f"/orders/{order_id}", json={"comment": "срочно"})
    assert resp.status_code == 403  # a — водитель, не диспетчер


def test_update_order_allowed_for_dispatcher(client, db_engine):
    a, _, _ = seed_queue(db_engine, ["A", "B", "C"])
    login_as(db_engine, a)
    order_id = client.post("/orders", json={"route": "t", "queue_type": "long"}).json()["id"]

    dispatcher_id = _make_user(db_engine, "Dispatcher", is_dispatcher=True)
    login_as(db_engine, dispatcher_id)
    resp = client.patch(f"/orders/{order_id}", json={"comment": "срочно"})
    assert resp.status_code == 200


# --- POST /orders/{id}/replace ---


def test_replace_order_requires_dispatcher_role(client, db_engine):
    a, _, _ = seed_queue(db_engine, ["A", "B", "C"])
    login_as(db_engine, a)
    order_id = client.post("/orders", json={"route": "t", "queue_type": "long"}).json()["id"]

    resp = client.post(f"/orders/{order_id}/replace", json={"route": "t2", "queue_type": "short"})
    assert resp.status_code == 403


def test_replace_order_allowed_for_dispatcher(client, db_engine):
    a, _, _ = seed_queue(db_engine, ["A", "B", "C"])
    login_as(db_engine, a)
    order_id = client.post("/orders", json={"route": "t", "queue_type": "long"}).json()["id"]

    dispatcher_id = _make_user(db_engine, "Dispatcher", is_dispatcher=True)
    login_as(db_engine, dispatcher_id)
    resp = client.post(f"/orders/{order_id}/replace", json={"route": "t2", "queue_type": "short"})
    assert resp.status_code == 200


# --- /admin/*: admin-only ---


def test_admin_endpoints_require_admin_role(client, db_engine):
    a, _, _ = seed_queue(db_engine, ["A", "B", "C"])
    login_as(db_engine, a)  # обычный водитель, не админ

    assert client.post("/admin/users", json={"name": "X", "username": "x"}).status_code == 403
    assert client.patch(f"/admin/users/{a}/roles", json={"is_admin": True}).status_code == 403
    assert client.post(f"/admin/users/{a}/queue/short").status_code == 403
    assert client.delete(f"/admin/users/{a}/queue/long").status_code == 403
    assert client.post("/admin/queue/long/reorder", json={"user_ids": [a]}).status_code == 403


def test_admin_create_user_with_roles_and_queues(client, db_engine):
    admin_id = _make_user(db_engine, "Admin", is_admin=True)
    login_as(db_engine, admin_id)

    resp = client.post(
        "/admin/users",
        json={
            "name": "Новый Водитель",
            "username": "newdriver",
            "is_driver": True,
            "queue_types": ["long", "short"],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_driver"] is True
    assert body["is_dispatcher"] is False

    users = client.get("/users").json()
    created = next(u for u in users if u["name"] == "Новый Водитель")
    assert created["is_driver"] is True
    assert created["user_id"] in queue_order(client, "long")
    assert created["user_id"] in queue_order(client, "short")


def test_admin_create_user_duplicate_username_rejected(client, db_engine):
    admin_id = _make_user(db_engine, "Admin", is_admin=True)
    login_as(db_engine, admin_id)

    resp = client.post("/admin/users", json={"name": "Дубль", "username": "admin"})
    assert resp.status_code == 400


def test_admin_create_user_queue_without_driver_role_rejected(client, db_engine):
    admin_id = _make_user(db_engine, "Admin", is_admin=True)
    login_as(db_engine, admin_id)

    resp = client.post(
        "/admin/users",
        json={"name": "X", "username": "x", "queue_types": ["long"]},
    )
    assert resp.status_code == 400


def test_admin_update_roles_partial(client, db_engine):
    admin_id = _make_user(db_engine, "Admin", is_admin=True)
    target_id = _make_user(db_engine, "Target", is_driver=True)
    login_as(db_engine, admin_id)

    resp = client.patch(f"/admin/users/{target_id}/roles", json={"is_dispatcher": True})
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_driver"] is True  # не тронуто
    assert body["is_dispatcher"] is True  # добавлено


def test_admin_add_and_remove_from_queue(client, db_engine):
    admin_id = _make_user(db_engine, "Admin", is_admin=True)
    driver_id = _make_user(db_engine, "Driver", is_driver=True)
    login_as(db_engine, admin_id)

    resp = client.post(f"/admin/users/{driver_id}/queue/long")
    assert resp.status_code == 200
    assert driver_id in queue_order(client, "long")

    resp = client.delete(f"/admin/users/{driver_id}/queue/long")
    assert resp.status_code == 200
    assert driver_id not in queue_order(client, "long")


def test_admin_reorder_queue(client, db_engine):
    a, b, c = seed_queue(db_engine, ["A", "B", "C"])
    admin_id = _make_user(db_engine, "Admin", is_admin=True)
    login_as(db_engine, admin_id)

    resp = client.post("/admin/queue/long/reorder", json={"user_ids": [c, a, b]})
    assert resp.status_code == 200
    assert queue_order(client, "long") == [c, a, b]


def test_admin_reorder_queue_rejects_mismatched_set(client, db_engine):
    a, b, _ = seed_queue(db_engine, ["A", "B", "C"])
    admin_id = _make_user(db_engine, "Admin", is_admin=True)
    login_as(db_engine, admin_id)

    resp = client.post("/admin/queue/long/reorder", json={"user_ids": [a, b]})  # без c
    assert resp.status_code == 400
