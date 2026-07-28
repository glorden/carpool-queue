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
.../start-integration/how-auth-works/auth-flow-web) — обратите внимание,
именно id.vk.ru, не id.vk.com (последний недоступен из части сетей/
окружений). Прямая работа с API без JS SDK официально поддерживается VK —
теряются только элементы быстрого входа (One Tap и т.п.), не нужные при
чистом server-side redirect. Старый oauth.vk.com полностью deprecated,
актуальная система — VK ID на базе OAuth 2.1 с обязательным PKCE.

exchange_code() возвращает user_id прямо в теле ответа — официальная
схема «без SDK, обмен на бэкенде» не предусматривает отдельного вызова
/oauth2/user_info для этого флоу (подтверждено диаграммой и примером
ответа в доке); более ранняя версия этого кода делала такой вызов
отдельно и падала, потому что VK ID требует client_id и там тоже.
client_secret передаётся в теле запроса — подтверждено рабочим на проде.
"""
import base64
import hashlib
import secrets
from urllib.parse import urlencode

import requests

from app.config import VK_CLIENT_ID, VK_CLIENT_SECRET, VK_REDIRECT_URI

VK_ID_AUTHORIZE_URL = "https://id.vk.ru/authorize"
VK_ID_TOKEN_URL = "https://id.vk.ru/oauth2/auth"


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
    """Обменивает authorization code на access_token + user_id.

    Бросает ValueError, если VK вернул ошибку вместо токенов.
    """
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "code_verifier": code_verifier,
        "client_id": VK_CLIENT_ID,
        "client_secret": VK_CLIENT_SECRET,
        "redirect_uri": VK_REDIRECT_URI,
    }
    if device_id:
        data["device_id"] = device_id

    response = requests.post(VK_ID_TOKEN_URL, data=data, timeout=10)
    result = response.json()
    if "access_token" not in result or "user_id" not in result:
        raise ValueError(f"VK ID token exchange failed: {result}")
    return result
