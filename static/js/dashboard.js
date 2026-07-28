const API_BASE = ""; // тот же origin, отдельный base не нужен

const QUEUE_TYPE_LABELS = { long: "Дальний", short: "Короткий" };

function createTypeBadge(queueType) {
    const badge = document.createElement("span");
    badge.className = `type-tag type-tag-${queueType}`;
    badge.textContent = QUEUE_TYPE_LABELS[queueType] || queueType;
    return badge;
}

async function loadQueue(queueType) {
    const res = await fetch(`${API_BASE}/queue?queue_type=${queueType}`);
    return await res.json();
}

let currentUser = null;

function updateAuthGate() {
    document.getElementById("auth-gated").hidden = !currentUser;
    document.getElementById("login-prompt").hidden = !!currentUser;
}

function renderQueue(queue, queueType) {
    const list = document.getElementById(`queue-list-${queueType}`);
    const currentUserId = currentUser ? String(currentUser.user_id) : null;

    list.innerHTML = "";
    queue.forEach((entry) => {
        const li = document.createElement("li");
        li.textContent = entry.name;
        if (currentUserId && String(entry.user_id) === currentUserId) {
            li.classList.add("current-user");
        }
        list.appendChild(li);
    });
}

let currentQueues = { long: [], short: [] };

async function refreshQueues() {
    currentQueues.long = await loadQueue("long");
    currentQueues.short = await loadQueue("short");
    renderQueue(currentQueues.long, "long");
    renderQueue(currentQueues.short, "short");
}

async function loadPendingOrders() {
    const res = await fetch(`${API_BASE}/orders/pending`);
    const orders = await res.json();
    return orders;
}

function renderPendingOrders(orders) {
    const list = document.getElementById("pending-list");
    const currentUserId = currentUser ? String(currentUser.user_id) : null;
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
        textSpan.appendChild(createTypeBadge(order.queue_type));
        textSpan.appendChild(
            document.createTextNode(` #${order.id} ${routeText} — ${offeredText}`)
        );
        li.appendChild(textSpan);

        const isOfferedToMe =
            currentUserId &&
            order.offered_to &&
            String(order.offered_to.user_id) === currentUserId;

        const actions = document.createElement("span");
        actions.className = "order-actions";

        if (isOfferedToMe) {
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
        } else {
            const selfAssignBtn = document.createElement("button");
            selfAssignBtn.textContent = "Самоназначиться";
            selfAssignBtn.className = "btn-self-assign";
            selfAssignBtn.addEventListener("click", () =>
                selfAssignOrder(order.id)
            );

            actions.appendChild(selfAssignBtn);
        }

        const cancelBtn = document.createElement("button");
        cancelBtn.textContent = "Отмена заказа";
        cancelBtn.className = "btn-cancel";
        cancelBtn.addEventListener("click", () => cancelOrder(order.id));
        actions.appendChild(cancelBtn);

        li.appendChild(actions);
        list.appendChild(li);
    });
}

async function refreshPending() {
    const pending = await loadPendingOrders();
    renderPendingOrders(pending);
}

async function cancelOrder(orderId) {
    if (!confirm("Отменить заказ?")) {
        return;
    }

    try {
        const res = await fetch(`${API_BASE}/orders/${orderId}/cancel`, {
            method: "POST",
        });

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || "Ошибка при отмене заказа");
        }

        await refreshPending();
        await refreshMyOrders();
        await refreshQueues();
    } catch (e) {
        alert(e.message);
    }
}

async function respondToOrder(orderId, response) {
    if (!currentUser) {
        alert("Сначала войдите через VK.");
        return;
    }

    try {
        const res = await fetch(`${API_BASE}/orders/${orderId}/respond`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ response: response }),
        });

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || "Ошибка при ответе на заказ");
        }

        await refreshPending();
        await refreshMyOrders();
        await refreshQueues();
    } catch (e) {
        alert(e.message);
    }
}

async function selfAssignOrder(orderId) {
    if (!currentUser) {
        alert("Сначала войдите через VK.");
        return;
    }

    const reason = prompt("Укажите причину самоназначения:");
    if (reason === null) {
        return;
    }

    const trimmedReason = reason.trim();
    if (!trimmedReason) {
        alert("Причина обязательна для самоназначения.");
        return;
    }

    try {
        const res = await fetch(`${API_BASE}/orders/${orderId}/self-assign`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ reason: trimmedReason }),
        });

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || "Ошибка самоназначения");
        }

        await refreshPending();
        await refreshMyOrders();
        await refreshQueues();
    } catch (e) {
        alert(e.message);
    }
}

async function loadMyOrders() {
    if (!currentUser) {
        return [];
    }

    const res = await fetch(
        `${API_BASE}/orders?status=assigned&user_id=${currentUser.user_id}`
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
        textSpan.appendChild(createTypeBadge(order.queue_type));
        textSpan.appendChild(document.createTextNode(` #${order.id} ${routeText}`));
        li.appendChild(textSpan);

        const actions = document.createElement("span");
        actions.className = "order-actions";

        const completeBtn = document.createElement("button");
        completeBtn.textContent = "Завершить";
        completeBtn.className = "btn-complete";
        completeBtn.addEventListener("click", () => completeOrder(order.id));

        const cancelBtn = document.createElement("button");
        cancelBtn.textContent = "Отмена заказа";
        cancelBtn.className = "btn-cancel";
        cancelBtn.addEventListener("click", () => cancelOrder(order.id));

        actions.appendChild(completeBtn);
        actions.appendChild(cancelBtn);
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

function checkRouteLatin() {
    const routeInput = document.getElementById("route");
    const warning = document.getElementById("route-latin-warning");
    warning.hidden = !/[a-zA-Z]/.test(routeInput.value);
}

async function handleCreateOrder(event) {
    event.preventDefault();

    const routeInput = document.getElementById("route");
    const commentInput = document.getElementById("comment");
    const statusEl = document.getElementById("create-order-status");
    const queueTypeInput = document.querySelector('input[name="queue_type"]:checked');

    statusEl.classList.remove("error");

    if (!queueTypeInput) {
        statusEl.textContent = "Выберите тип заказа: дальний или короткий.";
        statusEl.classList.add("error");
        return;
    }

    const body = {
        route: routeInput.value || null,
        comment: commentInput.value || null,
        queue_type: queueTypeInput.value,
    };

    statusEl.textContent = "Создаю...";

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
        document
            .querySelectorAll('input[name="queue_type"]')
            .forEach((input) => (input.checked = false));
        checkRouteLatin();

        await refreshPending();
    } catch (e) {
        statusEl.textContent = e.message;
        statusEl.classList.add("error");
    }
}

async function init() {
    currentUser = await window.sessionReady;
    updateAuthGate();

    if (!currentUser) {
        return;
    }

    await refreshQueues();
    await refreshPending();
    await refreshMyOrders();

    document
        .getElementById("create-order-form")
        .addEventListener("submit", handleCreateOrder);
    document
        .getElementById("route")
        .addEventListener("input", checkRouteLatin);
}

init();
