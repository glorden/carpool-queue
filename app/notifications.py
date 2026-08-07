import logging
import random

import requests

from app.config import SITE_URL, VK_GROUP_TOKEN, VK_PEER_ID

logger = logging.getLogger(__name__)

VK_API_VERSION = "5.199"

QUEUE_TYPE_LABELS = {"long": "дальний", "short": "короткий"}


def _driver_mention(driver_name: str, driver_vk_id: int | None) -> str:
    return f"[id{driver_vk_id}|{driver_name}]" if driver_vk_id else driver_name


def _queue_type_label(queue_type) -> str:
    return QUEUE_TYPE_LABELS.get(queue_type, queue_type)


def _send(message: str, order_id: int) -> None:
    """Best-effort отправка в общую беседу VK: если VK не настроен или
    недоступен, просто логируем и не прерываем основной сценарий (заказы
    не должны зависеть от стороннего API)."""
    if not VK_GROUP_TOKEN or not VK_PEER_ID:
        return

    try:
        response = requests.post(
            "https://api.vk.com/method/messages.send",
            data={
                "access_token": VK_GROUP_TOKEN,
                "v": VK_API_VERSION,
                "peer_id": VK_PEER_ID,
                "random_id": random.randint(1, 2**31 - 1),
                "message": message,
            },
            timeout=5,
        )
        result = response.json()
        if "error" in result:
            logger.warning("VK notify failed for order %s: %s", order_id, result["error"])
    except requests.RequestException:
        logger.warning("VK notify request failed for order %s", order_id, exc_info=True)


def notify_offer(
    order,
    driver_name: str,
    driver_vk_id: int | None = None,
    declined_by: str | None = None,
) -> None:
    """Шлёт сообщение в общую беседу VK о том, кому сейчас предложен заказ.

    Если declined_by задан — значит заказ уже кто-то отклонил, и это
    сообщение говорит, кто именно и что заказ уходит следующему в очереди.
    """
    driver_mention = _driver_mention(driver_name, driver_vk_id)
    route_text = order.route or "маршрут не указан"
    type_label = _queue_type_label(order.queue_type)

    lines = (
        [f"{declined_by} отказался."]
        if declined_by
        else [f"Новый заказ №{order.id} ({type_label})."]
    )
    lines.append(f"{route_text}.")
    if order.comment:
        lines.append(f"{order.comment}.")
    lines.append(f"Предлагаю взять заказ {driver_mention}.")
    lines.append(SITE_URL)

    _send("\n".join(lines), order.id)


def notify_accepted(order, driver_name: str, driver_vk_id: int | None = None) -> None:
    """Шлёт сообщение в общую беседу VK о том, что заказ принят конкретным водителем."""
    driver_mention = _driver_mention(driver_name, driver_vk_id)
    type_label = _queue_type_label(order.queue_type)
    _send(f"{driver_mention} взял заказ №{order.id} ({type_label}).", order.id)


def notify_self_assigned(
    order, driver_name: str, reason: str, driver_vk_id: int | None = None
) -> None:
    """Шлёт сообщение в общую беседу VK о самоназначении на заказ вне очереди."""
    driver_mention = _driver_mention(driver_name, driver_vk_id)
    type_label = _queue_type_label(order.queue_type)
    _send(
        f"Самоназначение вне очереди на заказ №{order.id} ({type_label}): {driver_mention}.\nПричина: {reason}",
        order.id,
    )


def notify_assigned(
    order,
    driver_name: str,
    dispatcher_name: str,
    driver_vk_id: int | None = None,
    reassigned: bool = False,
) -> None:
    """Шлёт сообщение в общую беседу VK о прямом назначении/переназначении
    заказа диспетчером вне очереди (см. ARCHITECTURE.md, «Роли и права
    доступа»)."""
    driver_mention = _driver_mention(driver_name, driver_vk_id)
    type_label = _queue_type_label(order.queue_type)
    verb = "переназначил" if reassigned else "назначил"
    _send(
        f"Диспетчер {dispatcher_name} {verb} заказ №{order.id} ({type_label}) водителю {driver_mention}.",
        order.id,
    )
