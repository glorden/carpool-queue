from fastapi import FastAPI, Depends
from sqlmodel import Session, select

from app.database import get_session
from app.models.user import User
from app.models.queue import QueuePosition

app = FastAPI(title="Carpool Queue")


@app.get("/")
def read_root():
    return {"status": "ok", "message": "Carpool queue service is running"}


@app.get("/queue")
def get_queue(session: Session = Depends(get_session)):
    """Возвращает список пользователей в порядке очереди."""
    statement = (
        select(QueuePosition, User)
        .join(User, QueuePosition.user_id == User.id)
        .order_by(QueuePosition.position)
    )
    results = session.exec(statement).all()

    return [
        {"position": qp.position, "user_id": user.id, "name": user.name}
        for qp, user in results
    ]
