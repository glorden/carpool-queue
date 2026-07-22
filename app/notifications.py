import logging
import random

import requests

from app.config import SITE_URL, VK_GROUP_TOKEN, VK_PEER_ID

logger = logging.getLogger(__name__)

VK_API_VERSION = "5.199"


def notify_offer(order, driver_name: str, driver_vk_id: int | None = None) -> None:
    """Шлёт сообщение в общую беседу VK о том, кому сейчас предложен заказ.

    Если у водителя известен vk_id — тегает его ([id...|Имя]), иначе просто
    пишет имя текстом.

    Best-effort: если VK не настроен или недоступен, просто логируем
    и не прерываем основной сценарий (создание/переход заказа не должны
    зависеть от стороннего API).
    """
    if not VK_GROUP_TOKEN or not VK_PEER_ID:
        return

    driver_mention = (
        f"[id{driver_vk_id}|{driver_name}]" if driver_vk_id else driver_name
    )
    route_text = order.route or "маршрут не указан"

    lines = [
        f"Новый заказ №{order.id}.",
        f"{route_text}.",
    ]
    if order.comment:
        lines.append(f"{order.comment}.")
    lines.append(f"Предлагаю взять заказ {driver_mention}.")
    lines.append(SITE_URL)

    message = "\n".join(lines)

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
            logger.warning("VK notify failed for order %s: %s", order.id, result["error"])
    except requests.RequestException:
        logger.warning("VK notify request failed for order %s", order.id, exc_info=True)
