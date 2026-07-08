import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./carpool.db")
SECRET_KEY = os.getenv("SECRET_KEY", "change-me-later")
