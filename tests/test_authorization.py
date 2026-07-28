"""Тесты реальных identity-проверок на защищённых эндпоинтах — Шаг 26,
закрывает техдолг, описанный в ARCHITECTURE.md («Технический долг»).
Шаг 25 (см. tests/test_auth.py) дал только механизм сессии; здесь —
сама проверка, что действие выполняет тот, кому это разрешено.
"""
from tests.conftest import login_as, logout_test_client, seed_queue


# --- 401: без сессии вообще ---


def test_create_order_requires_session(client):
    resp = client.post("/orders", json={"route": "t", "queue_type": "long"})
    assert resp.status_code == 401


def test_respond_requires_session(client, db_engine):
    a, _, _ = seed_queue(db_engine, ["A", "B", "C"])
    login_as(db_engine, a)
    order_id = client.post("/orders", json={"route": "t", "queue_type": "long"}).json()["id"]

    logout_test_client()
    resp = client.post(f"/orders/{order_id}/respond", json={"response": "accepted"})
    assert resp.status_code == 401


def test_self_assign_requires_session(client, db_engine):
    a, _, _ = seed_queue(db_engine, ["A", "B", "C"])
    login_as(db_engine, a)
    order_id = client.post("/orders", json={"route": "t", "queue_type": "long"}).json()["id"]

    logout_test_client()
    resp = client.post(f"/orders/{order_id}/self-assign", json={"reason": "рядом"})
    assert resp.status_code == 401


def test_complete_requires_session(client, db_engine):
    a, _, _ = seed_queue(db_engine, ["A", "B", "C"])
    login_as(db_engine, a)
    order_id = client.post("/orders", json={"route": "t", "queue_type": "long"}).json()["id"]
    client.post(f"/orders/{order_id}/respond", json={"response": "accepted"})

    logout_test_client()
    resp = client.post(f"/orders/{order_id}/complete")
    assert resp.status_code == 401


def test_cancel_requires_session(client, db_engine):
    a, _, _ = seed_queue(db_engine, ["A", "B", "C"])
    login_as(db_engine, a)
    order_id = client.post("/orders", json={"route": "t", "queue_type": "long"}).json()["id"]

    logout_test_client()
    resp = client.post(f"/orders/{order_id}/cancel")
    assert resp.status_code == 401


def test_price_endpoints_require_session(client, db_engine):
    seed_queue(db_engine, ["A", "B", "C"])

    assert (
        client.post(
            "/price", json={"category": "tour", "name": "Тест", "price_text": "1000"}
        ).status_code
        == 401
    )
    assert client.put("/price/1", json={"name": "Тест2"}).status_code == 401
    assert client.delete("/price/1").status_code == 401


def test_read_endpoints_require_session(client, db_engine):
    """Шаг 27: сайт закрыт под VK ID целиком — данные-отдающие GET-эндпоинты
    тоже требуют сессию, не только мутирующие (см. ARCHITECTURE.md)."""
    seed_queue(db_engine, ["A", "B", "C"])

    assert client.get("/users").status_code == 401
    assert client.get("/queue").status_code == 401
    assert client.get("/orders").status_code == 401
    assert client.get("/orders/pending").status_code == 401
    assert client.get("/price").status_code == 401
    assert client.get("/price/log").status_code == 401
    assert client.get("/activity").status_code == 401
    assert client.get("/statistics/summary").status_code == 401


# --- 403: сессия есть, но действие не твоё ---


def test_respond_rejects_offer_not_yours(client, db_engine):
    a, b, _ = seed_queue(db_engine, ["A", "B", "C"])
    login_as(db_engine, a)
    order_id = client.post("/orders", json={"route": "t", "queue_type": "long"}).json()["id"]
    # оффер сейчас у a (первый в очереди) — не у b

    login_as(db_engine, b)
    resp = client.post(f"/orders/{order_id}/respond", json={"response": "accepted"})
    assert resp.status_code == 403


def test_complete_rejects_non_assignee(client, db_engine):
    a, b, _ = seed_queue(db_engine, ["A", "B", "C"])
    login_as(db_engine, a)
    order_id = client.post("/orders", json={"route": "t", "queue_type": "long"}).json()["id"]
    login_as(db_engine, a)
    client.post(f"/orders/{order_id}/respond", json={"response": "accepted"})

    login_as(db_engine, b)
    resp = client.post(f"/orders/{order_id}/complete")
    assert resp.status_code == 403


def test_cancel_pending_rejects_non_creator(client, db_engine):
    a, b, _ = seed_queue(db_engine, ["A", "B", "C"])
    login_as(db_engine, a)
    order_id = client.post("/orders", json={"route": "t", "queue_type": "long"}).json()["id"]

    login_as(db_engine, b)
    resp = client.post(f"/orders/{order_id}/cancel")
    assert resp.status_code == 403


def test_cancel_pending_allows_creator(client, db_engine):
    a, _, _ = seed_queue(db_engine, ["A", "B", "C"])
    login_as(db_engine, a)
    order_id = client.post("/orders", json={"route": "t", "queue_type": "long"}).json()["id"]

    resp = client.post(f"/orders/{order_id}/cancel")
    assert resp.status_code == 200



# Во всех трёх тестах ниже важно развести роли "создатель" и
# "исполнитель" по-настоящему: оффер на pending-заказ уходит первому в
# очереди (a), а не тому, кто его создал — значит, чтобы created_by и
# assigned_to не совпали случайно, создаёт заказ b (не первый в
# очереди), а отвечает a (первый).


def test_cancel_assigned_rejects_third_party(client, db_engine):
    a, b, c = seed_queue(db_engine, ["A", "B", "C"])
    login_as(db_engine, b)  # b создаёт, сам не в начале очереди
    order_id = client.post("/orders", json={"route": "t", "queue_type": "long"}).json()["id"]
    login_as(db_engine, a)  # a — первый в очереди, заказ достаётся ему
    client.post(f"/orders/{order_id}/respond", json={"response": "accepted"})

    login_as(db_engine, c)  # c — ни создатель, ни исполнитель
    resp = client.post(f"/orders/{order_id}/cancel")
    assert resp.status_code == 403


def test_cancel_assigned_allows_creator(client, db_engine):
    a, b, _ = seed_queue(db_engine, ["A", "B", "C"])
    login_as(db_engine, b)  # b создаёт
    order_id = client.post("/orders", json={"route": "t", "queue_type": "long"}).json()["id"]
    login_as(db_engine, a)  # a — исполнитель
    client.post(f"/orders/{order_id}/respond", json={"response": "accepted"})

    login_as(db_engine, b)  # создатель, не исполнитель
    resp = client.post(f"/orders/{order_id}/cancel")
    assert resp.status_code == 200


def test_cancel_assigned_allows_assignee(client, db_engine):
    a, b, _ = seed_queue(db_engine, ["A", "B", "C"])
    login_as(db_engine, b)  # b создаёт
    order_id = client.post("/orders", json={"route": "t", "queue_type": "long"}).json()["id"]
    login_as(db_engine, a)  # a — исполнитель
    client.post(f"/orders/{order_id}/respond", json={"response": "accepted"})

    resp = client.post(f"/orders/{order_id}/cancel")  # всё ещё a — исполнитель, не создатель
    assert resp.status_code == 200


# --- identity из сессии реально попадает в данные, не из тела ---


def test_create_order_records_creator(client, db_engine):
    a, _, _ = seed_queue(db_engine, ["A", "B", "C"])
    login_as(db_engine, a)

    order = client.post("/orders", json={"route": "t", "queue_type": "long"}).json()
    assert order["created_by"] == a


def test_price_log_user_id_comes_from_session_not_body(client, db_engine):
    a, b, _ = seed_queue(db_engine, ["A", "B", "C"])

    login_as(db_engine, a)
    item = client.post(
        "/price", json={"category": "tour", "name": "Тест", "price_text": "1000"}
    ).json()

    login_as(db_engine, b)
    client.put(f"/price/{item['id']}", json={"price_text": "2000"})

    login_as(db_engine, a)
    client.delete(f"/price/{item['id']}")

    log = client.get("/price/log").json()
    actions = {entry["action"]: entry["user_id"] for entry in log}
    assert actions["created"] == a
    assert actions["updated"] == b
    assert actions["deleted"] == a
