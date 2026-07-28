"""Тесты входа через VK ID: механика PKCE (app/vk_oauth.py) и весь flow
через сессию (app/auth.py, роуты /auth/vk/* в app/main.py). См.
ARCHITECTURE.md, «Вход через VK ID».
"""
import base64
import hashlib
from urllib.parse import parse_qs, urlparse

from sqlmodel import Session

from app.models.user import User
from app.vk_oauth import build_authorize_url, generate_pkce_pair
from tests.conftest import seed_queue


def test_pkce_pair_challenge_matches_verifier():
    verifier, challenge = generate_pkce_pair()

    expected_digest = hashlib.sha256(verifier.encode("ascii")).digest()
    expected_challenge = (
        base64.urlsafe_b64encode(expected_digest).rstrip(b"=").decode("ascii")
    )

    assert challenge == expected_challenge
    # code_verifier по RFC 7636 — 43-128 символов, url-safe алфавит
    assert 43 <= len(verifier) <= 128
    assert all(c.isalnum() or c in "-_" for c in verifier)


def test_pkce_pairs_are_unique():
    verifier1, challenge1 = generate_pkce_pair()
    verifier2, challenge2 = generate_pkce_pair()

    assert verifier1 != verifier2
    assert challenge1 != challenge2


def test_build_authorize_url_contains_required_params():
    url = build_authorize_url(state="test-state", code_challenge="test-challenge")

    assert url.startswith("https://id.vk.ru/authorize?")
    assert "response_type=code" in url
    assert "state=test-state" in url
    assert "code_challenge=test-challenge" in url
    assert "code_challenge_method=S256" in url
    assert "redirect_uri=" in url
    assert "client_id=" in url


def _mock_vk_responses(monkeypatch, vk_user_id):
    """Подменяет сетевой вызов VK ID — app.main импортировал его по имени
    (`from app.vk_oauth import ...`), поэтому патчить нужно ссылку в
    app.main, а не в app.vk_oauth."""
    monkeypatch.setattr(
        "app.main.exchange_code",
        lambda code, verifier, device_id: {
            "access_token": "fake-token",
            "user_id": vk_user_id,
        },
    )


def _do_vk_login(client, monkeypatch, vk_user_id):
    """Проходит /auth/vk/login -> /auth/vk/callback с замоканными сетевыми
    вызовами (state/code_verifier берутся из настоящей cookie-сессии,
    полученной на первом шаге). Возвращает response самого callback."""
    login_resp = client.get("/auth/vk/login", follow_redirects=False)
    location = login_resp.headers["location"]
    state = parse_qs(urlparse(location).query)["state"][0]

    _mock_vk_responses(monkeypatch, vk_user_id)

    return client.get(
        f"/auth/vk/callback?code=test-code&state={state}", follow_redirects=False
    )


def test_me_without_session_is_unauthenticated(client):
    resp = client.get("/me")
    assert resp.status_code == 200
    assert resp.json() == {"authenticated": False}


def test_new_vk_id_redirects_to_link_account_screen(client, db_engine, monkeypatch):
    seed_queue(db_engine, ["A", "B"])

    callback_resp = _do_vk_login(client, monkeypatch, vk_user_id=111)

    assert callback_resp.headers["location"] == "/static/link-account.html"
    assert client.get("/me").json() == {"authenticated": False}


def test_link_candidates_without_pending_link_returns_403(client):
    resp = client.get("/auth/vk/link-candidates")
    assert resp.status_code == 403


def test_full_self_link_flow(client, db_engine, monkeypatch):
    a, b = seed_queue(db_engine, ["A", "B"])

    _do_vk_login(client, monkeypatch, vk_user_id=222)

    candidates = client.get("/auth/vk/link-candidates").json()
    assert {c["user_id"] for c in candidates} == {a, b}

    link_resp = client.post("/auth/vk/link", json={"user_id": a})
    assert link_resp.status_code == 200
    assert link_resp.json() == {"user_id": a, "name": "A"}

    me = client.get("/me").json()
    assert me == {"authenticated": True, "user_id": a, "name": "A", "username": "a"}

    with Session(db_engine) as session:
        assert session.get(User, a).vk_id == 222


def test_link_to_already_linked_user_returns_400(client, db_engine, monkeypatch):
    (a,) = seed_queue(db_engine, ["A"])
    with Session(db_engine) as session:
        user = session.get(User, a)
        user.vk_id = 333
        session.add(user)
        session.commit()

    _do_vk_login(client, monkeypatch, vk_user_id=444)
    resp = client.post("/auth/vk/link", json={"user_id": a})

    assert resp.status_code == 400


def test_existing_vk_id_logs_in_directly_without_link_screen(client, db_engine, monkeypatch):
    (a,) = seed_queue(db_engine, ["A"])
    with Session(db_engine) as session:
        user = session.get(User, a)
        user.vk_id = 555
        session.add(user)
        session.commit()

    callback_resp = _do_vk_login(client, monkeypatch, vk_user_id=555)

    assert callback_resp.headers["location"] == "/"
    me = client.get("/me").json()
    assert me == {"authenticated": True, "user_id": a, "name": "A", "username": "a"}


def test_no_unclaimed_users_denies_login(client, db_engine, monkeypatch):
    (a,) = seed_queue(db_engine, ["A"])
    with Session(db_engine) as session:
        user = session.get(User, a)
        user.vk_id = 666
        session.add(user)
        session.commit()

    callback_resp = _do_vk_login(client, monkeypatch, vk_user_id=777)

    assert callback_resp.headers["location"] == "/static/login-denied.html"
    assert client.get("/me").json() == {"authenticated": False}


def test_invalid_state_returns_400(client, monkeypatch):
    client.get("/auth/vk/login", follow_redirects=False)
    _mock_vk_responses(monkeypatch, vk_user_id=1)

    resp = client.get("/auth/vk/callback?code=test-code&state=wrong-state")

    assert resp.status_code == 400


def test_logout_clears_session(client, db_engine, monkeypatch):
    (a,) = seed_queue(db_engine, ["A"])
    _do_vk_login(client, monkeypatch, vk_user_id=888)
    client.post("/auth/vk/link", json={"user_id": a})
    assert client.get("/me").json()["authenticated"] is True

    logout_resp = client.post("/auth/logout")

    assert logout_resp.json() == {"status": "ok"}
    assert client.get("/me").json() == {"authenticated": False}
