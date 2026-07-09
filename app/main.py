from datetime import datetime
from fastapi import FastAPI, Depends
from sqlmodel import Session, select
from app.database import get_session
from app.models.user import User
from app.models.queue import QueuePosition
from app.models.order import Order, OrderOffer, OfferResponse, OrderStatus
from pydantic import BaseModel


class OrderCreate(BaseModel):
    route: str | None = None
    comment: str | None = None


class OrderRespond(BaseModel):
    user_id: int
    response: str  # "accepted" или "declined"


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


@app.post("/orders/{order_id}/respond")
def respond_to_order(
    order_id: int,
    respond_in: OrderRespond,
    session: Session = Depends(get_session),
):
    """Принять или отклонить предложенный заказ."""
    order = session.get(Order, order_id)
    if order is None:
        return {"error": "Order not found"}

    offer = session.exec(
        select(OrderOffer)
        .where(OrderOffer.order_id == order_id)
        .where(OrderOffer.response == OfferResponse.pending)
        .order_by(OrderOffer.offered_at.desc())
    ).first()

    if offer is None:
        return {"error": "No pending offer for this order"}

    if respond_in.response == "accepted":
        offer.response = OfferResponse.accepted
        offer.responded_at = datetime.utcnow()
        session.add(offer)

        order.status = OrderStatus.assigned
        order.assigned_to = respond_in.user_id
        session.add(order)

        # Пользователь уходит в конец очереди
        max_position = session.exec(
            select(QueuePosition.position).order_by(QueuePosition.position.desc())
        ).first()
        user_qp = session.exec(
            select(QueuePosition).where(QueuePosition.user_id == respond_in.user_id)
        ).first()
        user_qp.position = max_position + 1
        session.add(user_qp)

        session.commit()
        session.refresh(order)
        return order

    elif respond_in.response == "declined":
        offer.response = OfferResponse.declined
        offer.responded_at = datetime.utcnow()
        session.add(offer)

        # Ищем следующего по очереди (по кругу)
        current_qp = session.exec(
            select(QueuePosition).where(QueuePosition.user_id == respond_in.user_id)
        ).first()
        next_qp = session.exec(
            select(QueuePosition)
            .where(QueuePosition.position > current_qp.position)
            .order_by(QueuePosition.position)
        ).first()
        if next_qp is None:
            # дошли до конца очереди — возвращаемся к первому
            next_qp = session.exec(
                select(QueuePosition).order_by(QueuePosition.position)
            ).first()

        new_offer = OrderOffer(order_id=order.id, user_id=next_qp.user_id)
        session.add(new_offer)

        session.commit()
        session.refresh(order)
        return order

    else:
        return {"error": "response must be 'accepted' or 'declined'"}