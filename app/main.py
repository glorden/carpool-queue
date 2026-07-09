from fastapi import FastAPI, Depends
from sqlmodel import Session, select

from app.database import get_session
from app.models.user import User
from app.models.queue import QueuePosition
from app.models.order import Order, OrderOffer
from pydantic import BaseModel


class OrderCreate(BaseModel):
    route: str | None = None
    comment: str | None = None

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
@app.post("/orders")
def create_order(
    order_in: OrderCreate,
    session: Session = Depends(get_session),
):
    """Создаёт новый заказ и сразу предлагает его первому в очереди."""
    order = Order(route=order_in.route, comment=order_in.comment)
    session.add(order)
    session.commit()
    session.refresh(order)

    # Находим первого по очереди
    first_in_queue = session.exec(
        select(QueuePosition).order_by(QueuePosition.position)
    ).first()

    if first_in_queue is not None:
        offer = OrderOffer(order_id=order.id, user_id=first_in_queue.user_id)
        session.add(offer)
        session.commit()

    return order