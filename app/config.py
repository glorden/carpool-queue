import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./carpool.db")
SECRET_KEY = os.getenv("SECRET_KEY", "change-me-later")

VK_GROUP_TOKEN = os.getenv("VK_GROUP_TOKEN")
VK_PEER_ID = os.getenv("VK_PEER_ID")
SITE_URL = os.getenv("SITE_URL", "https://zakaz.glorden.ru/")

# Вход через VK ID (OAuth) — отдельно от VK_GROUP_TOKEN/VK_PEER_ID выше
# (те — уведомления от сообщества, это — логин людей). См. ARCHITECTURE.md,
# «Вход через VK ID».
VK_CLIENT_ID = os.getenv("VK_CLIENT_ID")
VK_CLIENT_SECRET = os.getenv("VK_CLIENT_SECRET")
VK_REDIRECT_URI = os.getenv("VK_REDIRECT_URI", "https://zakaz.glorden.ru/auth/vk/callback")

# false — только для локальной отладки, если Secure-cookie почему-то не
# работает на 127.0.0.1. На проде всегда true (трафик снаружи — HTTPS).
SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "true").lower() == "true"
