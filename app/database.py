from sqlmodel import create_engine, Session

from app.config import DATABASE_URL

# connect_args нужен только для SQLite, чтобы разрешить работу
# из нескольких потоков (uvicorn использует несколько воркеров запроса)
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


def get_session():
    """Отдаёт сессию для работы с базой. Используется в роутерах."""
    with Session(engine) as session:
        yield session
