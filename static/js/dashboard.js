const API_BASE = ""; // тот же origin, отдельный base не нужен

async function loadQueue() {
    const res = await fetch(`${API_BASE}/queue`);
    const queue = await res.json();
    return queue;
}

function populateUserSelector(queue) {
    const select = document.getElementById("current-user");
    const savedUserId = localStorage.getItem("carpool_user_id");

    queue.forEach((entry) => {
        const option = document.createElement("option");
        option.value = entry.user_id;
        option.textContent = entry.name;
        if (savedUserId && String(entry.user_id) === savedUserId) {
            option.selected = true;
        }
        select.appendChild(option);
    });

    select.addEventListener("change", () => {
        if (select.value) {
            localStorage.setItem("carpool_user_id", select.value);
        } else {
            localStorage.removeItem("carpool_user_id");
        }
        renderQueue(currentQueue);
        refreshPending();
        refreshMyOrders();
    });
}

function renderQueue(queue) {
    const list = document.getElementById("queue-list");
    const savedUserId = localStorage.getItem("carpool_user_id");

    list.innerHTML = "";
    queue.forEach((entry) => {
        const li = document.createElement("li");
        li.textContent = `${entry.name} (позиция ${entry.position})`;
        if (savedUserId && String(entry.user_id) === savedUserId) {
            li.classList.add("current-user");
        }
        list.appendChild(li);
    });
}

let currentQueue = [];

async function loadPendingOrders() {
    const res = await fetch(`${API_BASE}/orders/pending`);
    const orders = await res.json();
    return orders;
}

function renderPendingOrders(orders) {
    const list = document.getElementById("pending-list");
    const currentUserId = localStorage.getItem("carpool_user_id");
    list.innerHTML = "";

    if (orders.length === 0) {
        const li = document.createElement("li");
        li.textContent = "Нет активных заказов";
        list.appendChild(li);
        return;
    }

    orders.forEach((order) => {
        const li = document.createElement("li");

        const routeText = order.route
            ? order.route
            : "Маршрут не указан";

        const offeredText = order.offered_to
            ? `предложено водителю: ${order.offered_to.name}`
            : "Предложение не найдено";

        const textSpan = document.createElement("span");
        textSpan.textContent = `#${order.id} ${routeText} — ${offeredText}`;
        li.appendChild(textSpan);

        const isOfferedToMe =
            currentUserId &&
            order.offered_to &&
            String(order.offered_to.user_id) === currentUserId;

        if (isOfferedToMe) {
            const actions = document.createElement("span");
            actions.className = "order-actions";

            const acceptBtn = document.createElement("button");
            acceptBtn.textContent = "Принять";
            acceptBtn.className = "btn-accept";
            acceptBtn.addEventListener("click", () =>
                respondToOrder(order.id, "accepted")
            );

            const declineBtn = document.createElement("button");
            declineBtn.textContent = "Отклонить";
            declineBtn.className = "btn-decline";
            declineBtn.addEventListener("click", () =>
                respondToOrder(order.id, "declined")
            );

            actions.appendChild(acceptBtn);
            actions.appendChild(declineBtn);
            li.appendChild(actions);
        }

        list.appendChild(li);
    });
}

async function refreshPending() {
    const pending = await loadPendingOrders();
    renderPendingOrders(pending);
}

async function respondToOrder(orderId, response) {
    const currentUserId = localStorage.getItem("carpool_user_id");

    if (!currentUserId) {
        alert("Сначала выберите себя в верхней части страницы.");
        return;
    }

    try {
        const res = await fetch(`${API_BASE}/orders/${orderId}/respond`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                user_id: Number(currentUserId),
                response: response,
            }),
        });

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || "Ошибка при ответе на заказ");
        }

        await refreshPending();
        await refreshMyOrders();

        currentQueue = await loadQueue();
        renderQueue(currentQueue);
    } catch (e) {
        alert(e.message);
    }
}

async function loadMyOrders() {
    const currentUserId = localStorage.getItem("carpool_user_id");

    if (!currentUserId) {
        return [];
    }

    const res = await fetch(
        `${API_BASE}/orders?status=assigned&user_id=${currentUserId}`
    );

    return await res.json();
}

function renderMyOrders(orders) {
    const list = document.getElementById("my-orders-list");
    list.innerHTML = "";

    if (orders.length === 0) {
        const li = document.createElement("li");
        li.textContent = "Нет заказов в пути";
        list.appendChild(li);
        return;
    }

    orders.forEach((order) => {
        const li = document.createElement("li");

        const routeText = order.route
            ? order.route
            : "Маршрут не указан";

        const textSpan = document.createElement("span");
        textSpan.textContent = `#${order.id} ${routeText}`;
        li.appendChild(textSpan);

        const actions = document.createElement("span");
        actions.className = "order-actions";

        const completeBtn = document.createElement("button");
        completeBtn.textContent = "Завершить";
        completeBtn.className = "btn-complete";
        completeBtn.addEventListener("click", () => completeOrder(order.id));

        actions.appendChild(completeBtn);
        li.appendChild(actions);

        list.appendChild(li);
    });
}

async function refreshMyOrders() {
    const orders = await loadMyOrders();
    renderMyOrders(orders);
}

async function completeOrder(orderId) {
    try {
        const res = await fetch(`${API_BASE}/orders/${orderId}/complete`, {
            method: "POST",
        });

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || "Ошибка завершения заказа");
        }

        await refreshMyOrders();
    } catch (e) {
        alert(e.message);
    }
}

async function handleCreateOrder(event) {
    event.preventDefault();

    const routeInput = document.getElementById("route");
    const commentInput = document.getElementById("comment");
    const statusEl = document.getElementById("create-order-status");

    const body = {
        route: routeInput.value || null,
        comment: commentInput.value || null,
    };

    statusEl.textContent = "Создаю...";
    statusEl.classList.remove("error");

    try {
        const res = await fetch(`${API_BASE}/orders`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || "Ошибка создания заказа");
        }

        const order = await res.json();

        statusEl.textContent = `Заказ №${order.id} создан`;

        routeInput.value = "";
        commentInput.value = "";

        await refreshPending();
    } catch (e) {
        statusEl.textContent = e.message;
        statusEl.classList.add("error");
    }
}

async function init() {
    currentQueue = await loadQueue();

    populateUserSelector(currentQueue);
    renderQueue(currentQueue);

    await refreshPending();
    await refreshMyOrders();

    document
        .getElementById("create-order-form")
        .addEventListener("submit", handleCreateOrder);
}

init();