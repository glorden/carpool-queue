from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException, Query
from sqlmodel import Session, select
from app.database import get_session
from app.models.user import User
from app.models.queue import QueuePosition
from app.models.order import Order, OrderOffer, OfferResponse, OrderStatus
from app.models.price import PriceItem, PriceLogEntry
from app.models.activity import ActivityLog
from app.notifications import notify_accepted, notify_offer, notify_self_assigned
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse


class OrderCreate(BaseModel):
    route: str | None = None
    comment: str | None = None


class OrderRespond(BaseModel):
    user_id: int
    response: str  # "accepted" или "declined"


class OrderSelfAssign(BaseModel):
    user_id: int
    reason: str


class PriceItemCreate(BaseModel):
    user_id: int
    category: str
    name: str
    price_text: str


class PriceItemUpdate(BaseModel):
    user_id: int
    category: str | None = None
    name: str | None = None
    price_text: str | None = None


def _price_snapshot(item: PriceItem) -> str:
    return f"{item.category} / {item.name} / {item.price_text}"


def _log_activity(
    session: Session,
    event_type: str,
    message: str,
    user_id: int | None = None,
    order_id: int | None = None,
) -> None:
    """Пишет запись в журнал действий (см. ARCHITECTURE.md, «Журнал действий»)."""
    entry = ActivityLog(
        event_type=event_type,
        message=message,
        user_id=user_id,
        order_id=order_id,
    )
    session.add(entry)
    session.commit()


app = FastAPI(title="Carpool Queue")
app.mount("/static", StaticFiles(directory="static", html=True), name="static")

@app.get("/")
def read_root():
    return FileResponse("static/index.html")


@app.get("/health")
def health_check():
    return {"status": "ok", "message": "Carpool queue service is running"}


@app.get("/users")
def list_users(session: Session = Depends(get_session)):
    """Возвращает всех пользователей, включая диспетчеров без очереди."""
    users = session.exec(select(User)).all()
    return [{"user_id": u.id, "name": u.name} for u in users]


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

@app.get("/orders", response_model=list[Order])
def list_orders(
    status: OrderStatus | None = None,
    user_id: int | None = None,
    limit: int = Query(default=100, le=500),
    session: Session = Depends(get_session),
):
    """Возвращает историю заказов с опциональной фильтрацией.

    - status: фильтр по статусу (pending/assigned/completed)
    - user_id: фильтр по исполнителю (assigned_to)
    - limit: максимум записей в ответе (по умолчанию 100, максимум 500)
    """
    statement = select(Order)

    if status is not None:
        statement = statement.where(Order.status == status)

    if user_id is not None:
        statement = statement.where(Order.assigned_to == user_id)

    statement = statement.order_by(Order.created_at.desc()).limit(limit)

    orders = session.exec(statement).all()
    return orders

@app.get("/orders/pending")
def list_pending_orders(session: Session = Depends(get_session)):
    """Возвращает заказы в статусе pending вместе с данными активного OrderOffer
    (кому сейчас предложен заказ)."""
    orders = session.exec(
        select(Order)
        .where(Order.status == OrderStatus.pending)
        .order_by(Order.created_at.desc())
    ).all()

    result = []
    for order in orders:
        offer = session.exec(
            select(OrderOffer)
            .where(OrderOffer.order_id == order.id)
            .where(OrderOffer.response == OfferResponse.pending)
            .order_by(OrderOffer.offered_at.desc())
        ).first()

        offered_to = None
        if offer is not None:
            user = session.get(User, offer.user_id)
            offered_to = {
                "user_id": offer.user_id,
                "name": user.name if user else None,
                "offered_at": offer.offered_at,
            }

        result.append(
            {
                "id": order.id,
                "route": order.route,
                "comment": order.comment,
                "status": order.status,
                "created_at": order.created_at,
                "offered_to": offered_to,
            }
        )

    return result

@app.post("/orders", response_model=Order)
def create_order(
    order_in: OrderCreate,
    session: Session = Depends(get_session),
):
    """Создаёт новый заказ и сразу предлагает его первому в очереди."""
    order = Order(route=order_in.route, comment=order_in.comment)
    session.add(order)
    session.commit()
    session.refresh(order)

    _log_activity(session, "order_created", f"Создан заказ №{order.id}", order_id=order.id)
    session.refresh(order)

    first_in_queue = session.exec(
        select(QueuePosition).order_by(QueuePosition.position)
    ).first()

    if first_in_queue is not None:
        offer = OrderOffer(order_id=order.id, user_id=first_in_queue.user_id)
        session.add(offer)
        session.commit()
        session.refresh(order)

        driver = session.get(User, first_in_queue.user_id)
        driver_name = driver.name if driver else "?"
        notify_offer(order, driver_name, driver.vk_id if driver else None)
        _log_activity(
            session,
            "order_offered",
            f"Заказ №{order.id} предложен {driver_name}",
            user_id=first_in_queue.user_id,
            order_id=order.id,
        )
        session.refresh(order)

    return order


@app.post("/orders/{order_id}/respond", response_model=Order)
def respond_to_order(
    order_id: int,
    respond_in: OrderRespond,
    session: Session = Depends(get_session),
):
    """Принять или отклонить предложенный заказ."""
    order = session.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    offer = session.exec(
        select(OrderOffer)
        .where(OrderOffer.order_id == order_id)
        .where(OrderOffer.response == OfferResponse.pending)
        .order_by(OrderOffer.offered_at.desc())
    ).first()

    if offer is None:
        raise HTTPException(status_code=400, detail="No pending offer for this order")

    if respond_in.response == "accepted":
        offer.response = OfferResponse.accepted
        offer.responded_at = datetime.utcnow()
        session.add(offer)

        order.status = OrderStatus.assigned
        order.assigned_to = respond_in.user_id
        session.add(order)

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

        driver = session.get(User, respond_in.user_id)
        driver_name = driver.name if driver else "?"
        notify_accepted(order, driver_name, driver.vk_id if driver else None)
        _log_activity(
            session,
            "order_accepted",
            f"{driver_name} принял заказ №{order.id}",
            user_id=respond_in.user_id,
            order_id=order.id,
        )
        _log_activity(
            session,
            "queue_changed",
            f"{driver_name} перемещён в конец очереди",
            user_id=respond_in.user_id,
            order_id=order.id,
        )
        session.refresh(order)

        return order

    elif respond_in.response == "declined":
        offer.response = OfferResponse.declined
        offer.responded_at = datetime.utcnow()
        session.add(offer)

        declining_user = session.get(User, respond_in.user_id)

        current_qp = session.exec(
            select(QueuePosition).where(QueuePosition.user_id == respond_in.user_id)
        ).first()
        next_qp = session.exec(
            select(QueuePosition)
            .where(QueuePosition.position > current_qp.position)
            .order_by(QueuePosition.position)
        ).first()
        if next_qp is None:
            next_qp = session.exec(
                select(QueuePosition).order_by(QueuePosition.position)
            ).first()

        new_offer = OrderOffer(order_id=order.id, user_id=next_qp.user_id)
        session.add(new_offer)

        session.commit()
        session.refresh(order)

        _log_activity(
            session,
            "order_declined",
            f"{declining_user.name if declining_user else '?'} отказался от заказа №{order.id}",
            user_id=respond_in.user_id,
            order_id=order.id,
        )

        driver = session.get(User, next_qp.user_id)
        driver_name = driver.name if driver else "?"
        notify_offer(
            order,
            driver_name,
            driver.vk_id if driver else None,
            declined_by=declining_user.name if declining_user else None,
        )
        _log_activity(
            session,
            "order_offered",
            f"Заказ №{order.id} предложен {driver_name}",
            user_id=next_qp.user_id,
            order_id=order.id,
        )
        session.refresh(order)

        return order

    else:
        raise HTTPException(
            status_code=400, detail="response must be 'accepted' or 'declined'"
        )


@app.post("/orders/{order_id}/self-assign", response_model=Order)
def self_assign_order(
    order_id: int,
    self_assign_in: OrderSelfAssign,
    session: Session = Depends(get_session),
):
    """Самоназначение на заказ вне очереди: водитель указывает причину
    (например, уже находится в городе подачи), сразу становится
    исполнителем и перемещается в конец очереди — так же, как при
    обычном принятии (`respond_to_order`, ветка `accepted`)."""
    order = session.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.status != OrderStatus.pending:
        raise HTTPException(
            status_code=400,
            detail=f"Order must be 'pending' to self-assign, current status: {order.status.value}",
        )

    reason = self_assign_in.reason.strip()
    if not reason:
        raise HTTPException(status_code=400, detail="reason is required")

    user_qp = session.exec(
        select(QueuePosition).where(QueuePosition.user_id == self_assign_in.user_id)
    ).first()
    if user_qp is None:
        raise HTTPException(status_code=400, detail="User is not in the driver queue")

    pending_offer = session.exec(
        select(OrderOffer)
        .where(OrderOffer.order_id == order_id)
        .where(OrderOffer.response == OfferResponse.pending)
        .order_by(OrderOffer.offered_at.desc())
    ).first()
    if pending_offer is not None:
        pending_offer.response = OfferResponse.declined
        pending_offer.responded_at = datetime.utcnow()
        session.add(pending_offer)

    offer = OrderOffer(
        order_id=order.id,
        user_id=self_assign_in.user_id,
        response=OfferResponse.accepted,
        responded_at=datetime.utcnow(),
    )
    session.add(offer)

    order.status = OrderStatus.assigned
    order.assigned_to = self_assign_in.user_id
    order.self_assign_reason = reason
    session.add(order)

    max_position = session.exec(
        select(QueuePosition.position).order_by(QueuePosition.position.desc())
    ).first()
    user_qp.position = max_position + 1
    session.add(user_qp)

    session.commit()
    session.refresh(order)

    driver = session.get(User, self_assign_in.user_id)
    driver_name = driver.name if driver else "?"
    notify_self_assigned(order, driver_name, reason, driver.vk_id if driver else None)
    _log_activity(
        session,
        "order_self_assigned",
        f"Самоназначение вне очереди на заказ №{order.id}: {driver_name}. Причина: {reason}",
        user_id=self_assign_in.user_id,
        order_id=order.id,
    )
    _log_activity(
        session,
        "queue_changed",
        f"{driver_name} перемещён в конец очереди",
        user_id=self_assign_in.user_id,
        order_id=order.id,
    )
    session.refresh(order)

    return order


@app.post("/orders/{order_id}/complete", response_model=Order)
def complete_order(
    order_id: int,
    session: Session = Depends(get_session),
):
    """Отмечает заказ как завершённый."""
    order = session.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.status != OrderStatus.assigned:
        raise HTTPException(
            status_code=400,
            detail=f"Order must be 'assigned' to complete, current status: {order.status.value}",
        )

    order.status = OrderStatus.completed
    order.completed_at = datetime.utcnow()
    session.add(order)
    session.commit()
    session.refresh(order)

    driver = session.get(User, order.assigned_to) if order.assigned_to else None
    _log_activity(
        session,
        "order_completed",
        f"{driver.name if driver else '?'} завершил заказ №{order.id}",
        user_id=order.assigned_to,
        order_id=order.id,
    )
    session.refresh(order)

    return order


@app.post("/orders/{order_id}/cancel", response_model=Order)
def cancel_order(
    order_id: int,
    session: Session = Depends(get_session),
):
    """Отменяет заказ. Если он был назначен водителю, возвращает того
    в начало очереди (см. ARCHITECTURE.md)."""
    order = session.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.status in (OrderStatus.completed, OrderStatus.cancelled):
        raise HTTPException(
            status_code=400,
            detail=f"Order cannot be cancelled from status: {order.status.value}",
        )

    if order.status == OrderStatus.assigned and order.assigned_to is not None:
        user_qp = session.exec(
            select(QueuePosition).where(QueuePosition.user_id == order.assigned_to)
        ).first()
        if user_qp is not None:
            others = session.exec(
                select(QueuePosition)
                .where(QueuePosition.user_id != order.assigned_to)
                .order_by(QueuePosition.position)
            ).all()

            # Вставляем сразу после текущего первого, не обгоняя его —
            # тот, кто первый по праву, не должен терять место из-за
            # чужой отмены (см. ARCHITECTURE.md)
            new_order = [others[0], user_qp, *others[1:]] if others else [user_qp]
            for position, qp in enumerate(new_order):
                qp.position = position
                session.add(qp)

            driver = session.get(User, order.assigned_to)
            _log_activity(
                session,
                "queue_changed",
                f"{driver.name if driver else '?'} возвращён в начало очереди",
                user_id=order.assigned_to,
                order_id=order.id,
            )

    order.status = OrderStatus.cancelled
    session.add(order)
    session.commit()
    session.refresh(order)

    _log_activity(
        session,
        "order_cancelled",
        f"Заказ №{order.id} отменён",
        user_id=order.assigned_to,
        order_id=order.id,
    )
    session.refresh(order)

    return order


@app.get("/price", response_model=list[PriceItem])
def list_price_items(session: Session = Depends(get_session)):
    """Возвращает весь прайс-лист."""
    statement = select(PriceItem).order_by(PriceItem.category, PriceItem.id)
    return session.exec(statement).all()


@app.post("/price", response_model=PriceItem)
def create_price_item(
    item_in: PriceItemCreate,
    session: Session = Depends(get_session),
):
    """Добавляет новую позицию прайса. Доступно любому пользователю
    (см. ARCHITECTURE.md), действие логируется."""
    item = PriceItem(
        category=item_in.category,
        name=item_in.name,
        price_text=item_in.price_text,
    )
    session.add(item)
    session.commit()
    session.refresh(item)

    log_entry = PriceLogEntry(
        user_id=item_in.user_id,
        action="created",
        item_name=item.name,
        new_value=_price_snapshot(item),
    )
    session.add(log_entry)
    session.commit()
    session.refresh(item)

    return item


@app.put("/price/{item_id}", response_model=PriceItem)
def update_price_item(
    item_id: int,
    item_in: PriceItemUpdate,
    session: Session = Depends(get_session),
):
    """Изменяет позицию прайса. Действие логируется."""
    item = session.get(PriceItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Price item not found")

    old_value = _price_snapshot(item)

    if item_in.category is not None:
        item.category = item_in.category
    if item_in.name is not None:
        item.name = item_in.name
    if item_in.price_text is not None:
        item.price_text = item_in.price_text

    session.add(item)
    session.commit()
    session.refresh(item)

    log_entry = PriceLogEntry(
        user_id=item_in.user_id,
        action="updated",
        item_name=item.name,
        old_value=old_value,
        new_value=_price_snapshot(item),
    )
    session.add(log_entry)
    session.commit()
    session.refresh(item)

    return item


@app.delete("/price/{item_id}")
def delete_price_item(
    item_id: int,
    user_id: int,
    session: Session = Depends(get_session),
):
    """Удаляет позицию прайса. Действие логируется."""
    item = session.get(PriceItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Price item not found")

    old_value = _price_snapshot(item)
    item_name = item.name

    session.delete(item)
    session.commit()

    log_entry = PriceLogEntry(
        user_id=user_id,
        action="deleted",
        item_name=item_name,
        old_value=old_value,
    )
    session.add(log_entry)
    session.commit()

    return {"status": "ok"}


@app.get("/price/log")
def list_price_log(
    limit: int = Query(default=100, le=500),
    session: Session = Depends(get_session),
):
    """Возвращает лог изменений прайса, новые сверху."""
    statement = (
        select(PriceLogEntry)
        .order_by(PriceLogEntry.created_at.desc())
        .limit(limit)
    )
    entries = session.exec(statement).all()

    result = []
    for entry in entries:
        user = session.get(User, entry.user_id)
        result.append(
            {
                "id": entry.id,
                "created_at": entry.created_at,
                "user_id": entry.user_id,
                "user_name": user.name if user else None,
                "action": entry.action,
                "item_name": entry.item_name,
                "old_value": entry.old_value,
                "new_value": entry.new_value,
            }
        )

    return result


@app.get("/activity")
def list_activity(
    user_id: int | None = None,
    order_id: int | None = None,
    event_type: str | None = None,
    limit: int = Query(default=100, le=500),
    session: Session = Depends(get_session),
):
    """Возвращает журнал действий, новые сверху, с опциональной фильтрацией
    по user_id/order_id/event_type. Отдельная сущность от истории заказов
    (см. ARCHITECTURE.md)."""
    statement = select(ActivityLog)

    if user_id is not None:
        statement = statement.where(ActivityLog.user_id == user_id)

    if order_id is not None:
        statement = statement.where(ActivityLog.order_id == order_id)

    if event_type is not None:
        statement = statement.where(ActivityLog.event_type == event_type)

    statement = statement.order_by(ActivityLog.created_at.desc()).limit(limit)
    entries = session.exec(statement).all()

    result = []
    for entry in entries:
        user = session.get(User, entry.user_id) if entry.user_id else None
        result.append(
            {
                "id": entry.id,
                "created_at": entry.created_at,
                "user_id": entry.user_id,
                "user_name": user.name if user else None,
                "order_id": entry.order_id,
                "event_type": entry.event_type,
                "message": entry.message,
            }
        )

    return result