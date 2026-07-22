import logging
import random

import requests

from app.config import VK_GROUP_TOKEN, VK_PEER_ID

logger = logging.getLogger(__name__)

VK_API_VERSION = "5.199"


def notify_offer(order, driver_name: str) -> None:
    """Шлёт сообщение в общую беседу VK о том, кому сейчас предложен заказ.

    Best-effort: если VK не настроен или недоступен, просто логируем
    и не прерываем основной сценарий (создание/переход заказа не должны
    зависеть от стороннего API).
    """
    if not VK_GROUP_TOKEN or not VK_PEER_ID:
        return

    route_text = order.route or "маршрут не указан"
    message = f"Заказ #{order.id} ({route_text}) предложен: {driver_name}"

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
