import logging
import secrets
from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException, Query, Request
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select
from starlette.middleware.sessions import SessionMiddleware
from app.auth import (
    get_current_user_optional,
    get_current_user_required,
    require_admin,
    require_dispatcher,
    require_driver,
)
from app.config import SECRET_KEY, SESSION_COOKIE_SECURE
from app.database import get_session
from app.models.user import User
from app.models.queue import QueuePosition, QueueType
from app.models.order import Order, OrderOffer, OfferResponse, OrderStatus
from app.models.price import PriceItem, PriceLogEntry
from app.models.activity import ActivityLog
from app.notifications import (
    notify_accepted,
    notify_assigned,
    notify_offer,
    notify_self_assigned,
)
from app.vk_oauth import (
    build_authorize_url,
    exchange_code,
    generate_pkce_pair,
)
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from fastapi.openapi.utils import get_openapi


class OrderCreate(BaseModel):
    route: str | None = None
    comment: str | None = None
    queue_type: QueueType


class OrderRespond(BaseModel):
    response: str  # "accepted" или "declined"


class OrderSelfAssign(BaseModel):
    reason: str


class OrderAssign(BaseModel):
    driver_user_id: int


class OrderUpdate(BaseModel):
    route: str | None = None
    comment: str | None = None


class VkLinkRequest(BaseModel):
    user_id: int


class AdminUserCreate(BaseModel):
    name: str
    username: str
    is_driver: bool = False
    is_dispatcher: bool = False
    is_admin: bool = False
    queue_types: list[QueueType] = []


class AdminRolesUpdate(BaseModel):
    is_driver: bool | None = None
    is_dispatcher: bool | None = None
    is_admin: bool | None = None


class AdminQueueReorder(BaseModel):
    user_ids: list[int]


class PriceItemCreate(BaseModel):
    category: str
    name: str
    price_text: str


class PriceItemUpdate(BaseModel):
    category: str | None = None
    name: str | None = None
    price_text: str | None = None


def _price_snapshot(item: PriceItem) -> str:
    return f"{item.category} / {item.name} / {item.price_text}"


def _user_dict(user: User) -> dict:
    return {
        "user_id": user.id,
        "name": user.name,
        "is_driver": user.is_driver,
        "is_dispatcher": user.is_dispatcher,
        "is_admin": user.is_admin,
    }


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


def _create_order(
    order_in: OrderCreate,
    session: Session,
    current_user: User,
    replaces_order_id: int | None = None,
) -> Order:
    """Создаёт новый заказ и сразу предлагает его первому в очереди
    соответствующего типа. Общая логика для POST /orders и
    POST /orders/{id}/replace (см. ARCHITECTURE.md, «Редактирование и
    замена заказа») — во втором случае вызывается с заполненным
    replaces_order_id, связывающим новый заказ со старым."""
    order = Order(
        route=order_in.route,
        comment=order_in.comment,
        queue_type=order_in.queue_type,
        created_by=current_user.id,
        replaces_order_id=replaces_order_id,
    )
    session.add(order)
    session.commit()
    session.refresh(order)

    _log_activity(session, "order_created", f"Создан заказ №{order.id}", order_id=order.id)
    session.refresh(order)

    first_in_queue = session.exec(
        select(QueuePosition)
        .where(QueuePosition.queue_type == order.queue_type)
        .order_by(QueuePosition.position)
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


def _cancel_order(order: Order, session: Session, current_user: User) -> None:
    """Отменяет заказ. Если он был назначен водителю, возвращает того
    в начало очереди (см. ARCHITECTURE.md). Общая логика для
    POST /orders/{id}/cancel и POST /orders/{id}/replace — мутирует
    order на месте, ничего не возвращает. Бросает HTTPException (400/403)
    при недопустимом статусе/владении."""
    if order.status in (OrderStatus.completed, OrderStatus.cancelled):
        raise HTTPException(
            status_code=400,
            detail=f"Order cannot be cancelled from status: {order.status.value}",
        )

    # Диспетчер и админ могут отменить любой заказ (см. ARCHITECTURE.md,
    # «Роли и права доступа») — проверка владения ниже только для остальных.
    # created_by может быть None для заказов, созданных до Шага 26 —
    # для них сверять личность не с чем, разрешаем любому залогиненному
    # (см. ARCHITECTURE.md, «Технический долг»)
    if not (current_user.is_dispatcher or current_user.is_admin):
        if order.status == OrderStatus.pending:
            if order.created_by is not None and order.created_by != current_user.id:
                raise HTTPException(status_code=403, detail="Order was created by someone else")
        elif order.status == OrderStatus.assigned:
            known_owners = {uid for uid in (order.created_by, order.assigned_to) if uid is not None}
            if known_owners and current_user.id not in known_owners:
                raise HTTPException(status_code=403, detail="Order is not yours")

    if order.status == OrderStatus.assigned and order.assigned_to is not None:
        user_qp = session.exec(
            select(QueuePosition)
            .where(QueuePosition.user_id == order.assigned_to)
            .where(QueuePosition.queue_type == order.queue_type)
        ).first()
        if user_qp is not None:
            others = session.exec(
                select(QueuePosition)
                .where(QueuePosition.user_id != order.assigned_to)
                .where(QueuePosition.queue_type == order.queue_type)
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


logger = logging.getLogger(__name__)

app = FastAPI(title="Carpool Queue", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    session_cookie="carpool_session",
    same_site="lax",
    https_only=SESSION_COOKIE_SECURE,
    max_age=60 * 60 * 24 * 90,
)
app.mount("/static", StaticFiles(directory="static", html=True), name="static")

@app.get("/")
def read_root():
    return FileResponse("static/index.html")


@app.get("/health")
def health_check():
    return {"status": "ok", "message": "Carpool queue service is running"}


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse("static/fav/favicon.ico")


@app.get("/sw.js", include_in_schema=False)
def service_worker():
    """Отдаётся с корня (не /static/), чтобы scope service worker'а по
    умолчанию покрывал весь сайт, а не только /static/* (см.
    ARCHITECTURE.md, «PWA»). media_type — явно, браузер отказывается
    регистрировать SW при неверном Content-Type."""
    return FileResponse("static/sw.js", media_type="text/javascript")


### /docs, /redoc, /openapi.json закрыты сессией (docs_url=None выше) —
### сайт целиком закрыт под VK ID, эти ручки не исключение (см. ARCHITECTURE.md) ###

@app.get("/openapi.json", include_in_schema=False)
def get_openapi_schema(current_user: User = Depends(get_current_user_required)):
    return get_openapi(title=app.title, version=app.version, routes=app.routes)


@app.get("/docs", include_in_schema=False)
def get_docs(current_user: User = Depends(get_current_user_required)):
    return get_swagger_ui_html(openapi_url="/openapi.json", title=app.title + " — Docs")


@app.get("/redoc", include_in_schema=False)
def get_redoc(current_user: User = Depends(get_current_user_required)):
    return get_redoc_html(openapi_url="/openapi.json", title=app.title + " — ReDoc")


@app.get("/users")
def list_users(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user_required),
):
    """Возвращает всех пользователей, включая диспетчеров без очереди."""
    users = session.exec(select(User)).all()
    return [_user_dict(u) for u in users]


@app.get("/queue")
def get_queue(
    queue_type: QueueType | None = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user_required),
):
    """Возвращает список пользователей в порядке очереди.

    Без queue_type — позиции из обеих очередей сразу (пользователь,
    состоящий в обеих, попадёт дважды, с полем queue_type в каждой
    записи); используется страницами, которым нужен просто список
    водителей, а не порядок конкретной очереди (история заказов,
    журнал действий). С queue_type — порядок только этой очереди,
    для отображения на дэшборде.
    """
    statement = select(QueuePosition, User).join(User, QueuePosition.user_id == User.id)
    if queue_type is not None:
        statement = statement.where(QueuePosition.queue_type == queue_type)
    statement = statement.order_by(QueuePosition.queue_type, QueuePosition.position)

    results = session.exec(statement).all()
    return [
        {
            "position": qp.position,
            "user_id": user.id,
            "name": user.name,
            "queue_type": qp.queue_type,
        }
        for qp, user in results
    ]

@app.get("/orders", response_model=list[Order])
def list_orders(
    status: OrderStatus | None = None,
    user_id: int | None = None,
    queue_type: QueueType | None = None,
    limit: int = Query(default=100, le=500),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user_required),
):
    """Возвращает историю заказов с опциональной фильтрацией.

    - status: фильтр по статусу (pending/assigned/completed)
    - user_id: фильтр по исполнителю (assigned_to)
    - queue_type: фильтр по типу очереди (long/short)
    - limit: максимум записей в ответе (по умолчанию 100, максимум 500)
    """
    statement = select(Order)

    if status is not None:
        statement = statement.where(Order.status == status)

    if user_id is not None:
        statement = statement.where(Order.assigned_to == user_id)

    if queue_type is not None:
        statement = statement.where(Order.queue_type == queue_type)

    statement = statement.order_by(Order.created_at.desc()).limit(limit)

    orders = session.exec(statement).all()
    return orders

@app.get("/orders/pending")
def list_pending_orders(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user_required),
):
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
                "queue_type": order.queue_type,
                "created_at": order.created_at,
                "offered_to": offered_to,
            }
        )

    return result

@app.post("/orders", response_model=Order)
def create_order(
    order_in: OrderCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user_required),
):
    """Создаёт новый заказ и сразу предлагает его первому в очереди
    соответствующего типа."""
    return _create_order(order_in, session, current_user)


@app.post("/orders/{order_id}/respond", response_model=Order)
def respond_to_order(
    order_id: int,
    respond_in: OrderRespond,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_driver),
):
    """Принять или отклонить предложенный заказ."""
    order = session.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    offer = session.exec(
        select(OrderOffer)
        .where(OrderOffer.order_id == order_id)
        .where(OrderOffer.user_id == current_user.id)
        .where(OrderOffer.response == OfferResponse.pending)
        .order_by(OrderOffer.offered_at.desc())
    ).first()

    if offer is None:
        raise HTTPException(status_code=403, detail="Order not offered to you")

    if respond_in.response == "accepted":
        offer.response = OfferResponse.accepted
        offer.responded_at = datetime.utcnow()
        session.add(offer)

        order.status = OrderStatus.assigned
        order.assigned_to = current_user.id
        session.add(order)

        max_position = session.exec(
            select(QueuePosition.position)
            .where(QueuePosition.queue_type == order.queue_type)
            .order_by(QueuePosition.position.desc())
        ).first()
        user_qp = session.exec(
            select(QueuePosition)
            .where(QueuePosition.user_id == current_user.id)
            .where(QueuePosition.queue_type == order.queue_type)
        ).first()
        user_qp.position = max_position + 1
        session.add(user_qp)

        session.commit()
        session.refresh(order)

        notify_accepted(order, current_user.name, current_user.vk_id)
        _log_activity(
            session,
            "order_accepted",
            f"{current_user.name} принял заказ №{order.id}",
            user_id=current_user.id,
            order_id=order.id,
        )
        _log_activity(
            session,
            "queue_changed",
            f"{current_user.name} перемещён в конец очереди",
            user_id=current_user.id,
            order_id=order.id,
        )
        session.refresh(order)

        return order

    elif respond_in.response == "declined":
        offer.response = OfferResponse.declined
        offer.responded_at = datetime.utcnow()
        session.add(offer)

        current_qp = session.exec(
            select(QueuePosition)
            .where(QueuePosition.user_id == current_user.id)
            .where(QueuePosition.queue_type == order.queue_type)
        ).first()
        next_qp = session.exec(
            select(QueuePosition)
            .where(QueuePosition.position > current_qp.position)
            .where(QueuePosition.queue_type == order.queue_type)
            .order_by(QueuePosition.position)
        ).first()
        if next_qp is None:
            next_qp = session.exec(
                select(QueuePosition)
                .where(QueuePosition.queue_type == order.queue_type)
                .order_by(QueuePosition.position)
            ).first()

        new_offer = OrderOffer(order_id=order.id, user_id=next_qp.user_id)
        session.add(new_offer)

        session.commit()
        session.refresh(order)

        _log_activity(
            session,
            "order_declined",
            f"{current_user.name} отказался от заказа №{order.id}",
            user_id=current_user.id,
            order_id=order.id,
        )

        driver = session.get(User, next_qp.user_id)
        driver_name = driver.name if driver else "?"
        notify_offer(
            order,
            driver_name,
            driver.vk_id if driver else None,
            declined_by=current_user.name,
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
    current_user: User = Depends(require_driver),
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
        select(QueuePosition)
        .where(QueuePosition.user_id == current_user.id)
        .where(QueuePosition.queue_type == order.queue_type)
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
        user_id=current_user.id,
        response=OfferResponse.accepted,
        responded_at=datetime.utcnow(),
    )
    session.add(offer)

    order.status = OrderStatus.assigned
    order.assigned_to = current_user.id
    order.self_assign_reason = reason
    session.add(order)

    max_position = session.exec(
        select(QueuePosition.position)
        .where(QueuePosition.queue_type == order.queue_type)
        .order_by(QueuePosition.position.desc())
    ).first()
    user_qp.position = max_position + 1
    session.add(user_qp)

    session.commit()
    session.refresh(order)

    notify_self_assigned(order, current_user.name, reason, current_user.vk_id)
    _log_activity(
        session,
        "order_self_assigned",
        f"Самоназначение вне очереди на заказ №{order.id}: {current_user.name}. Причина: {reason}",
        user_id=current_user.id,
        order_id=order.id,
    )
    _log_activity(
        session,
        "queue_changed",
        f"{current_user.name} перемещён в конец очереди",
        user_id=current_user.id,
        order_id=order.id,
    )
    session.refresh(order)

    return order


@app.post("/orders/{order_id}/assign", response_model=Order)
def assign_order(
    order_id: int,
    assign_in: OrderAssign,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_dispatcher),
):
    """Прямое назначение (или переназначение) заказа конкретному водителю
    диспетчером/админом, в обход обычного цикла предложений по очереди
    (см. ARCHITECTURE.md, «Роли и права доступа»)."""
    order = session.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.status not in (OrderStatus.pending, OrderStatus.assigned):
        raise HTTPException(
            status_code=400,
            detail=f"Order must be 'pending' or 'assigned' to assign, current status: {order.status.value}",
        )

    driver = session.get(User, assign_in.driver_user_id)
    if driver is None or not driver.is_driver:
        raise HTTPException(status_code=400, detail="Target user is not a driver")

    driver_qp = session.exec(
        select(QueuePosition)
        .where(QueuePosition.user_id == driver.id)
        .where(QueuePosition.queue_type == order.queue_type)
    ).first()
    if driver_qp is None:
        raise HTTPException(status_code=400, detail="Driver is not in the queue of this type")

    if order.status == OrderStatus.assigned and order.assigned_to == driver.id:
        raise HTTPException(status_code=400, detail="Order is already assigned to this driver")

    was_reassigned = order.status == OrderStatus.assigned
    previous_driver_id = order.assigned_to if was_reassigned else None

    if order.status == OrderStatus.pending:
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
        user_id=driver.id,
        response=OfferResponse.accepted,
        responded_at=datetime.utcnow(),
    )
    session.add(offer)

    # Переназначение: прежний исполнитель возвращается вторым в очередь —
    # та же логика вставки, что в cancel_order (не по его вине забрали
    # заказ, но обгонять честно первого он не должен)
    if was_reassigned and previous_driver_id is not None:
        previous_qp = session.exec(
            select(QueuePosition)
            .where(QueuePosition.user_id == previous_driver_id)
            .where(QueuePosition.queue_type == order.queue_type)
        ).first()
        if previous_qp is not None:
            others = session.exec(
                select(QueuePosition)
                .where(QueuePosition.user_id != previous_driver_id)
                .where(QueuePosition.queue_type == order.queue_type)
                .order_by(QueuePosition.position)
            ).all()
            new_order = [others[0], previous_qp, *others[1:]] if others else [previous_qp]
            for position, qp in enumerate(new_order):
                qp.position = position
                session.add(qp)

    order.status = OrderStatus.assigned
    order.assigned_to = driver.id
    session.add(order)

    # Новый исполнитель уходит в конец своей очереди — max берём уже с
    # учётом переиндексации выше (autoflush перед exec() отправляет ещё не
    # закоммиченные изменения в текущую транзакцию)
    max_position = session.exec(
        select(QueuePosition.position)
        .where(QueuePosition.queue_type == order.queue_type)
        .order_by(QueuePosition.position.desc())
    ).first()
    driver_qp.position = max_position + 1
    session.add(driver_qp)

    session.commit()
    session.refresh(order)

    notify_assigned(
        order, driver.name, current_user.name, driver.vk_id, reassigned=was_reassigned
    )
    verb = "переназначил" if was_reassigned else "назначил"
    _log_activity(
        session,
        "order_assigned",
        f"{current_user.name} {verb} заказ №{order.id} водителю {driver.name}",
        user_id=driver.id,
        order_id=order.id,
    )
    session.refresh(order)

    return order


@app.post("/orders/{order_id}/complete", response_model=Order)
def complete_order(
    order_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_driver),
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

    if order.assigned_to != current_user.id:
        raise HTTPException(status_code=403, detail="Order is not assigned to you")

    order.status = OrderStatus.completed
    order.completed_at = datetime.utcnow()
    session.add(order)
    session.commit()
    session.refresh(order)

    _log_activity(
        session,
        "order_completed",
        f"{current_user.name} завершил заказ №{order.id}",
        user_id=current_user.id,
        order_id=order.id,
    )
    session.refresh(order)

    return order


@app.post("/orders/{order_id}/cancel", response_model=Order)
def cancel_order(
    order_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user_required),
):
    """Отменяет заказ. Если он был назначен водителю, возвращает того
    в начало очереди (см. ARCHITECTURE.md)."""
    order = session.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    _cancel_order(order, session, current_user)

    return order


@app.patch("/orders/{order_id}", response_model=Order)
def update_order(
    order_id: int,
    order_in: OrderUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_dispatcher),
):
    """Частичное редактирование маршрута/комментария заказа «на месте»,
    без затрагивания очереди/офферов. Для смены queue_type или правки
    уже предложенного/назначенного заказа — POST /orders/{id}/replace
    (см. ARCHITECTURE.md, «Редактирование и замена заказа»)."""
    order = session.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.status not in (OrderStatus.pending, OrderStatus.assigned):
        raise HTTPException(
            status_code=400,
            detail=f"Order must be 'pending' or 'assigned' to edit, current status: {order.status.value}",
        )

    old_route, old_comment = order.route, order.comment

    if order_in.route is not None:
        order.route = order_in.route
    if order_in.comment is not None:
        order.comment = order_in.comment

    session.add(order)
    session.commit()
    session.refresh(order)

    changes = []
    if order.route != old_route:
        changes.append(f"маршрут «{old_route or '—'}» → «{order.route or '—'}»")
    if order.comment != old_comment:
        changes.append(f"комментарий «{old_comment or '—'}» → «{order.comment or '—'}»")

    if changes:
        _log_activity(
            session,
            "order_edited",
            f"Заказ №{order.id} изменён: " + "; ".join(changes),
            user_id=current_user.id,
            order_id=order.id,
        )
        session.refresh(order)

    return order


@app.post("/orders/{order_id}/replace", response_model=Order)
def replace_order(
    order_id: int,
    order_in: OrderCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_dispatcher),
):
    """Заменяет заказ новым: старый отменяется (`_cancel_order` — та же
    логика возврата в очередь, что у обычной отмены), новый создаётся
    сразу с предложением первому в очереди его queue_type
    (`_create_order`), со связью replaces_order_id на старый. Нужно для
    смены queue_type или содержательной правки уже предложенного/
    назначенного заказа — там, где простого PATCH /orders/{id}
    недостаточно (см. ARCHITECTURE.md)."""
    order = session.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    _cancel_order(order, session, current_user)

    new_order = _create_order(order_in, session, current_user, replaces_order_id=order.id)

    _log_activity(
        session,
        "order_replaced",
        f"Заказ №{order.id} заменён заказом №{new_order.id}",
        user_id=current_user.id,
        order_id=order.id,
    )
    _log_activity(
        session,
        "order_replaced",
        f"Заказ №{new_order.id} создан взамен заказа №{order.id}",
        user_id=current_user.id,
        order_id=new_order.id,
    )
    session.refresh(new_order)

    return new_order


@app.get("/price", response_model=list[PriceItem])
def list_price_items(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user_required),
):
    """Возвращает весь прайс-лист."""
    statement = select(PriceItem).order_by(PriceItem.category, PriceItem.id)
    return session.exec(statement).all()


@app.post("/price", response_model=PriceItem)
def create_price_item(
    item_in: PriceItemCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user_required),
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
        user_id=current_user.id,
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
    current_user: User = Depends(get_current_user_required),
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
        user_id=current_user.id,
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
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user_required),
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
        user_id=current_user.id,
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
    current_user: User = Depends(get_current_user_required),
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
    current_user: User = Depends(get_current_user_required),
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


@app.get("/statistics/summary")
def get_statistics_summary(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user_required),
):
    """Общая статистика по заказам и по водителям (см. ARCHITECTURE.md)."""
    orders = session.exec(select(Order)).all()

    overall = {"total": len(orders), "completed": 0, "active": 0, "cancelled": 0}
    received_by_driver: dict[int, int] = {}
    completed_by_driver: dict[int, int] = {}
    cancelled_by_driver: dict[int, int] = {}

    for order in orders:
        if order.status == OrderStatus.completed:
            overall["completed"] += 1
        elif order.status == OrderStatus.cancelled:
            overall["cancelled"] += 1
        else:  # pending или assigned
            overall["active"] += 1

        if order.assigned_to is not None:
            received_by_driver[order.assigned_to] = received_by_driver.get(order.assigned_to, 0) + 1
            if order.status == OrderStatus.completed:
                completed_by_driver[order.assigned_to] = completed_by_driver.get(order.assigned_to, 0) + 1
            elif order.status == OrderStatus.cancelled:
                cancelled_by_driver[order.assigned_to] = cancelled_by_driver.get(order.assigned_to, 0) + 1

    # distinct() — водитель, состоящий в обеих очередях (long и short),
    # иначе попал бы в разбивку дважды с одинаковыми числами (числа
    # считаются от Order.assigned_to, а не от QueuePosition)
    queue_users = session.exec(
        select(User).join(QueuePosition, QueuePosition.user_id == User.id).distinct()
    ).all()

    by_driver = [
        {
            "user_id": user.id,
            "name": user.name,
            "received": received_by_driver.get(user.id, 0),
            "completed": completed_by_driver.get(user.id, 0),
            "cancelled": cancelled_by_driver.get(user.id, 0),
        }
        for user in queue_users
    ]
    by_driver.sort(key=lambda d: d["received"], reverse=True)

    return {"overall": overall, "by_driver": by_driver}


### Администрирование: пользователи, роли, очередь (см. ARCHITECTURE.md,
### «Роли и права доступа») — веб-аналог scripts/add_user.py и
### scripts/reorder_queue.py, только для is_admin ###

@app.post("/admin/users")
def admin_create_user(
    user_in: AdminUserCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_admin),
):
    """Создаёт нового пользователя с ролями и, опционально, сразу ставит
    в конец указанных очередей."""
    existing = session.exec(select(User).where(User.username == user_in.username)).first()
    if existing is not None:
        raise HTTPException(status_code=400, detail="Username already taken")

    if user_in.queue_types and not user_in.is_driver:
        raise HTTPException(status_code=400, detail="Cannot add to a queue without driver role")

    user = User(
        name=user_in.name,
        username=user_in.username,
        is_driver=user_in.is_driver,
        is_dispatcher=user_in.is_dispatcher,
        is_admin=user_in.is_admin,
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    for qt in user_in.queue_types:
        max_position = session.exec(
            select(QueuePosition.position)
            .where(QueuePosition.queue_type == qt)
            .order_by(QueuePosition.position.desc())
        ).first()
        session.add(
            QueuePosition(user_id=user.id, queue_type=qt, position=(max_position or 0) + 1)
        )
    session.commit()

    return _user_dict(user)


@app.patch("/admin/users/{user_id}/roles")
def admin_update_roles(
    user_id: int,
    roles_in: AdminRolesUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_admin),
):
    """Частично обновляет роли пользователя (совмещение — просто несколько
    True одновременно)."""
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if roles_in.is_driver is not None:
        user.is_driver = roles_in.is_driver
    if roles_in.is_dispatcher is not None:
        user.is_dispatcher = roles_in.is_dispatcher
    if roles_in.is_admin is not None:
        user.is_admin = roles_in.is_admin

    session.add(user)
    session.commit()
    session.refresh(user)

    return _user_dict(user)


@app.post("/admin/users/{user_id}/queue/{queue_type}")
def admin_add_to_queue(
    user_id: int,
    queue_type: QueueType,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_admin),
):
    """Добавляет уже существующего водителя в конец указанной очереди."""
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.is_driver:
        raise HTTPException(status_code=400, detail="User does not have the driver role")

    existing = session.exec(
        select(QueuePosition)
        .where(QueuePosition.user_id == user_id)
        .where(QueuePosition.queue_type == queue_type)
    ).first()
    if existing is not None:
        raise HTTPException(status_code=400, detail="User is already in this queue")

    max_position = session.exec(
        select(QueuePosition.position)
        .where(QueuePosition.queue_type == queue_type)
        .order_by(QueuePosition.position.desc())
    ).first()
    qp = QueuePosition(user_id=user_id, queue_type=queue_type, position=(max_position or 0) + 1)
    session.add(qp)
    session.commit()
    session.refresh(qp)

    return {"user_id": user_id, "queue_type": queue_type, "position": qp.position}


@app.delete("/admin/users/{user_id}/queue/{queue_type}")
def admin_remove_from_queue(
    user_id: int,
    queue_type: QueueType,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_admin),
):
    """Убирает водителя из указанной очереди и переиндексирует оставшихся
    (0..n-1), чтобы не оставалось пропусков в position."""
    qp = session.exec(
        select(QueuePosition)
        .where(QueuePosition.user_id == user_id)
        .where(QueuePosition.queue_type == queue_type)
    ).first()
    if qp is None:
        raise HTTPException(status_code=404, detail="User is not in this queue")

    session.delete(qp)
    session.commit()

    remaining = session.exec(
        select(QueuePosition)
        .where(QueuePosition.queue_type == queue_type)
        .order_by(QueuePosition.position)
    ).all()
    for position, remaining_qp in enumerate(remaining):
        remaining_qp.position = position
        session.add(remaining_qp)
    session.commit()

    return {"status": "ok"}


@app.post("/admin/queue/{queue_type}/reorder")
def admin_reorder_queue(
    queue_type: QueueType,
    reorder_in: AdminQueueReorder,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_admin),
):
    """Переставляет порядок одной из очередей — список user_ids должен
    содержать ровно тех же людей, что сейчас в ней состоят (см.
    scripts/reorder_queue.py — та же валидация)."""
    if len(reorder_in.user_ids) != len(set(reorder_in.user_ids)):
        raise HTTPException(status_code=400, detail="Duplicate user_id in list")

    current_qps = session.exec(
        select(QueuePosition).where(QueuePosition.queue_type == queue_type)
    ).all()
    qp_by_user_id = {qp.user_id: qp for qp in current_qps}

    if set(qp_by_user_id.keys()) != set(reorder_in.user_ids):
        raise HTTPException(
            status_code=400,
            detail="user_ids must exactly match the current members of this queue",
        )

    for position, user_id in enumerate(reorder_in.user_ids):
        qp_by_user_id[user_id].position = position
        session.add(qp_by_user_id[user_id])

    session.commit()

    return {"queue_type": queue_type, "order": reorder_in.user_ids}


### Вход через VK ID (см. ARCHITECTURE.md, «Вход через VK ID») ###

@app.get("/auth/vk/login")
def vk_login(request: Request):
    """Начинает VK ID OAuth: готовит PKCE-пару и state, кладёт их в
    сессию (нужны на шаге callback), редиректит на VK."""
    verifier, challenge = generate_pkce_pair()
    state = secrets.token_urlsafe(32)
    request.session["oauth_state"] = state
    request.session["oauth_code_verifier"] = verifier
    return RedirectResponse(build_authorize_url(state, challenge))


@app.get("/auth/vk/callback")
def vk_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    device_id: str | None = None,
    error: str | None = None,
    session: Session = Depends(get_session),
):
    """Обрабатывает возврат с VK: сверяет state, обменивает code на
    access_token, определяет vk_id. Дальше три исхода — уже привязанный
    User (сразу сессия), свободный vk_id при наличии непривязанных User
    (экран самопривязки), или отказ (все User уже привязаны)."""
    if error or not code or not state:
        return RedirectResponse("/")

    expected_state = request.session.pop("oauth_state", None)
    verifier = request.session.pop("oauth_code_verifier", None)
    if not expected_state or state != expected_state or not verifier:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    try:
        token_data = exchange_code(code, verifier, device_id)
        vk_user_id = int(token_data["user_id"])
    except ValueError as exc:
        logger.warning("VK ID exchange failed: %s", exc)
        raise HTTPException(status_code=502, detail="VK ID недоступен, попробуйте позже")

    user = session.exec(select(User).where(User.vk_id == vk_user_id)).first()
    if user is not None:
        request.session["user_id"] = user.id
        return RedirectResponse("/")

    has_unclaimed = session.exec(select(User).where(User.vk_id.is_(None))).first()
    if has_unclaimed is None:
        return RedirectResponse("/static/login-denied.html")

    request.session["pending_vk_id"] = vk_user_id
    return RedirectResponse("/static/link-account.html")


@app.get("/auth/vk/link-candidates")
def vk_link_candidates(request: Request, session: Session = Depends(get_session)):
    """Список User без привязанного vk_id — для экрана самопривязки.
    Доступен только сразу после callback с новым vk_id (см. vk_callback)."""
    if "pending_vk_id" not in request.session:
        raise HTTPException(status_code=403, detail="No pending VK link in session")

    users = session.exec(select(User).where(User.vk_id.is_(None))).all()
    return [{"user_id": u.id, "name": u.name} for u in users]


@app.post("/auth/vk/link")
def vk_link(
    body: VkLinkRequest, request: Request, session: Session = Depends(get_session)
):
    """Завершает самопривязку: сохраняет vk_id, полученный на callback,
    в выбранного пользователя, сразу логинит его."""
    pending_vk_id = request.session.get("pending_vk_id")
    if pending_vk_id is None:
        raise HTTPException(status_code=400, detail="No pending VK link in session")

    user = session.get(User, body.user_id)
    if user is None or user.vk_id is not None:
        raise HTTPException(status_code=400, detail="User not available for linking")

    user.vk_id = pending_vk_id
    session.add(user)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail="This VK account is already linked")
    session.refresh(user)

    request.session.pop("pending_vk_id", None)
    request.session["user_id"] = user.id
    _log_activity(
        session,
        "vk_account_linked",
        f"{user.name} привязал VK-аккаунт",
        user_id=user.id,
    )

    return {"user_id": user.id, "name": user.name}


@app.post("/auth/logout")
def logout(request: Request):
    request.session.clear()
    return {"status": "ok"}


@app.get("/me")
def get_me(user: User | None = Depends(get_current_user_optional)):
    if user is None:
        return {"authenticated": False}
    return {"authenticated": True, "username": user.username, **_user_dict(user)}