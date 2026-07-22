import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./carpool.db")
SECRET_KEY = os.getenv("SECRET_KEY", "change-me-later")

VK_GROUP_TOKEN = os.getenv("VK_GROUP_TOKEN")
VK_PEER_ID = os.getenv("VK_PEER_ID")
