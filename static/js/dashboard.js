const API_BASE = "";  // тот же origin, отдельный base не нужен

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
    list.innerHTML = "";

    if (orders.length === 0) {
        const li = document.createElement("li");
        li.textContent = "Нет активных заказов";
        list.appendChild(li);
        return;
    }

    orders.forEach((order) => {
        const li = document.createElement("li");
        const routeText = order.route ? order.route : "(без маршрута)";
        const offeredText = order.offered_to
            ? `предложено: ${order.offered_to.name}`
            : "оффер не найден";
        li.textContent = `#${order.id} ${routeText} — ${offeredText}`;
        list.appendChild(li);
    });
}

async function refreshPending() {
    const pending = await loadPendingOrders();
    renderPendingOrders(pending);
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
        statusEl.textContent = `Заказ #${order.id} создан`;
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

    document
        .getElementById("create-order-form")
        .addEventListener("submit", handleCreateOrder);
}

init();