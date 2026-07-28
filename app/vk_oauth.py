"""VK ID OAuth 2.1 + PKCE — механика получения identity через VK.

Не путать с app/notifications.py (тот шлёт сообщения от имени сообщества
через VK_GROUP_TOKEN — другой API и другая задача). См. ARCHITECTURE.md,
«Вход через VK ID».

Модуль сознательно не импортирует ничего из app.database/app.models/сессий/
FastAPI — только сам протокол VK ID. Если когда-нибудь понадобится
переиспользовать его в другом проекте, единственное, что придётся
поменять, — прямой импорт app.config ниже на параметры функций.

Домен и пути эндпоинтов подтверждены официальной документацией
(id.vk.ru/about/business/go/docs/ru/vkid/latest/vk-id/connection/realization,
.../work-with-user-info/user-info) — обратите внимание, именно id.vk.ru,
не id.vk.com (последний недоступен из части сетей/окружений). Прямая
работа с API без JS SDK официально поддерживается VK — теряются только
элементы быстрого входа (One Tap и т.п.), не нужные при чистом
server-side redirect. Старый oauth.vk.com полностью deprecated,
актуальная система — VK ID на базе OAuth 2.1 с обязательным PKCE.

Не подтверждено документацией и помечено # СВЕРИТЬ по месту: точная форма
JSON-ответа /oauth2/user_info (структура result["user"]["user_id"] —
предположение по аналогии со старым VK API) и способ передачи
client_secret (в теле запроса, как сейчас, или в заголовке Authorization).
"""
import base64
import hashlib
import secrets
from urllib.parse import urlencode

import requests

from app.config import VK_CLIENT_ID, VK_CLIENT_SECRET, VK_REDIRECT_URI

VK_ID_AUTHORIZE_URL = "https://id.vk.ru/authorize"
VK_ID_TOKEN_URL = "https://id.vk.ru/oauth2/auth"
VK_ID_USERINFO_URL = "https://id.vk.ru/oauth2/user_info"


def generate_pkce_pair() -> tuple[str, str]:
    """Возвращает (code_verifier, code_challenge) для PKCE (S256)."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def build_authorize_url(state: str, code_challenge: str) -> str:
    """Собирает URL редиректа на страницу авторизации VK ID."""
    params = {
        "response_type": "code",
        "client_id": VK_CLIENT_ID,
        "redirect_uri": VK_REDIRECT_URI,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{VK_ID_AUTHORIZE_URL}?{urlencode(params)}"


def exchange_code(code: str, code_verifier: str, device_id: str | None) -> dict:
    """Обменивает authorization code на access_token.

    Бросает ValueError, если VK вернул ошибку вместо токена.
    """
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "code_verifier": code_verifier,
        "client_id": VK_CLIENT_ID,
        "client_secret": VK_CLIENT_SECRET,   # СВЕРИТЬ: тело или Basic-заголовок
        "redirect_uri": VK_REDIRECT_URI,
    }
    if device_id:
        data["device_id"] = device_id

    response = requests.post(VK_ID_TOKEN_URL, data=data, timeout=10)
    result = response.json()
    if "access_token" not in result:
        raise ValueError(f"VK ID token exchange failed: {result}")
    return result


def fetch_vk_user_id(access_token: str) -> int:
    """Возвращает numeric VK user id владельца access_token.

    Бросает ValueError, если ответ VK не содержит ожидаемых данных.
    """
    response = requests.post(
        VK_ID_USERINFO_URL, data={"access_token": access_token}, timeout=10
    )
    result = response.json()
    try:
        return int(result["user"]["user_id"])   # СВЕРИТЬ форму ответа
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"VK ID user_info failed: {result}") from exc
