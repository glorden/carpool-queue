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

function isDispatcherOrAdmin() {
    return !!currentUser && (currentUser.is_dispatcher || currentUser.is_admin);
}

function createAssignControl(order) {
    const wrap = document.createElement("span");
    wrap.className = "assign-control";

    const select = document.createElement("select");
    (currentQueues[order.queue_type] || []).forEach((entry) => {
        const option = document.createElement("option");
        option.value = entry.user_id;
        option.textContent = entry.name;
        select.appendChild(option);
    });

    const assignBtn = document.createElement("button");
    assignBtn.type = "button";
    assignBtn.textContent = "Назначить";
    assignBtn.className = "btn-assign";
    assignBtn.addEventListener("click", () => {
        if (!select.value) return;
        assignOrder(order.id, select.value);
    });

    wrap.appendChild(select);
    wrap.appendChild(assignBtn);
    return wrap;
}

function startEditOrder(li, order) {
    li.innerHTML = "";
    li.classList.add("order-editing");

    const row = document.createElement("div");
    row.className = "order-edit-row";

    const routeInput = document.createElement("input");
    routeInput.type = "text";
    routeInput.value = order.route || "";
    routeInput.placeholder = "Маршрут";
    routeInput.className = "order-edit-input";

    const commentInput = document.createElement("input");
    commentInput.type = "text";
    commentInput.value = order.comment || "";
    commentInput.placeholder = "Комментарий";
    commentInput.className = "order-edit-input";

    row.appendChild(routeInput);
    row.appendChild(commentInput);

    const actions = document.createElement("div");
    actions.className = "order-actions";

    const saveBtn = document.createElement("button");
    saveBtn.type = "button";
    saveBtn.textContent = "Сохранить";
    saveBtn.className = "btn-accept";
    saveBtn.addEventListener("click", async () => {
        try {
            // Значения шлём как есть (включая "") — на PATCH "" осознанно
            // очищает поле, null означает "не трогать" (см. ARCHITECTURE.md).
            // `|| null` здесь превратил бы очистку в молчаливый no-op.
            await updateOrder(order.id, {
                route: routeInput.value,
                comment: commentInput.value,
            });
            await refreshAllOrderLists();
        } catch (e) {
            alert(e.message);
        }
    });

    const cancelBtn = document.createElement("button");
    cancelBtn.type = "button";
    cancelBtn.textContent = "Отмена";
    cancelBtn.className = "btn-decline";
    cancelBtn.addEventListener("click", () => refreshAllOrderLists());

    actions.appendChild(saveBtn);
    actions.appendChild(cancelBtn);

    li.appendChild(row);
    li.appendChild(actions);
}

function startReplaceOrder(li, order) {
    li.innerHTML = "";
    li.classList.add("order-editing");

    const row = document.createElement("div");
    row.className = "order-edit-row";

    const routeInput = document.createElement("input");
    routeInput.type = "text";
    routeInput.value = order.route || "";
    routeInput.placeholder = "Маршрут";
    routeInput.className = "order-edit-input";

    const commentInput = document.createElement("input");
    commentInput.type = "text";
    commentInput.value = order.comment || "";
    commentInput.placeholder = "Комментарий";
    commentInput.className = "order-edit-input";

    row.appendChild(routeInput);
    row.appendChild(commentInput);

    const typeField = document.createElement("div");
    typeField.className = "order-type-field";
    const typeLabel = document.createElement("span");
    typeLabel.className = "order-type-label";
    typeLabel.textContent = "Тип заказа:";
    typeField.appendChild(typeLabel);
    ["long", "short"].forEach((qt) => {
        const label = document.createElement("label");
        label.className = "radio-label";
        const radio = document.createElement("input");
        radio.type = "radio";
        radio.name = `replace-queue-type-${order.id}`;
        radio.value = qt;
        radio.checked = qt === order.queue_type;
        label.appendChild(radio);
        label.appendChild(document.createTextNode(QUEUE_TYPE_LABELS[qt]));
        typeField.appendChild(label);
    });

    const actions = document.createElement("div");
    actions.className = "order-actions";

    const saveBtn = document.createElement("button");
    saveBtn.type = "button";
    saveBtn.textContent = "Заменить";
    saveBtn.className = "btn-accept";
    saveBtn.addEventListener("click", async () => {
        if (!confirm(`Заменить заказ №${order.id} новым? Старый будет отменён.`)) return;
        try {
            await replaceOrder(order.id, {
                route: routeInput.value || null,
                comment: commentInput.value || null,
                queue_type: typeField.querySelector("input:checked").value,
            });
            await refreshAllOrderLists();
        } catch (e) {
            alert(e.message);
        }
    });

    const cancelBtn = document.createElement("button");
    cancelBtn.type = "button";
    cancelBtn.textContent = "Отмена";
    cancelBtn.className = "btn-decline";
    cancelBtn.addEventListener("click", () => refreshAllOrderLists());

    actions.appendChild(saveBtn);
    actions.appendChild(cancelBtn);

    li.appendChild(row);
    li.appendChild(typeField);
    li.appendChild(actions);
}

function appendEditReplaceButtons(actions, order, li) {
    if (!isDispatcherOrAdmin()) return;

    const editBtn = document.createElement("button");
    editBtn.type = "button";
    editBtn.textContent = "Изменить";
    editBtn.className = "btn-edit";
    editBtn.addEventListener("click", () => startEditOrder(li, order));

    const replaceBtn = document.createElement("button");
    replaceBtn.type = "button";
    replaceBtn.textContent = "Заменить";
    replaceBtn.className = "btn-replace";
    replaceBtn.addEventListener("click", () => startReplaceOrder(li, order));

    actions.appendChild(editBtn);
    actions.appendChild(replaceBtn);
}

async function assignOrder(orderId, driverUserId) {
    try {
        const res = await fetch(`${API_BASE}/orders/${orderId}/assign`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ driver_user_id: Number(driverUserId) }),
        });

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || "Ошибка назначения");
        }

        await refreshPending();
        await refreshMyOrders();
        await refreshQueues();
        await refreshAllAssigned();
    } catch (e) {
        alert(e.message);
    }
}

async function updateOrder(orderId, fields) {
    const res = await fetch(`${API_BASE}/orders/${orderId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(fields),
    });
    if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Ошибка изменения заказа");
    }
    return res.json();
}

async function replaceOrder(orderId, body) {
    const res = await fetch(`${API_BASE}/orders/${orderId}/replace`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });
    if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Ошибка замены заказа");
    }
    return res.json();
}

async function refreshAllOrderLists() {
    await refreshPending();
    await refreshMyOrders();
    await refreshQueues();
    await refreshAllAssigned();
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

        if (isDispatcherOrAdmin()) {
            actions.appendChild(createAssignControl(order));
        }

        appendEditReplaceButtons(actions, order, li);

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

async function loadAllAssignedOrders() {
    const res = await fetch(`${API_BASE}/orders?status=assigned`);
    return await res.json();
}

function renderAllAssignedOrders(orders) {
    const list = document.getElementById("all-assigned-list");
    list.innerHTML = "";

    if (orders.length === 0) {
        const li = document.createElement("li");
        li.textContent = "Нет активных заказов";
        list.appendChild(li);
        return;
    }

    orders.forEach((order) => {
        const li = document.createElement("li");

        const routeText = order.route ? order.route : "Маршрут не указан";
        const textSpan = document.createElement("span");
        textSpan.appendChild(createTypeBadge(order.queue_type));
        textSpan.appendChild(document.createTextNode(` #${order.id} ${routeText}`));
        li.appendChild(textSpan);

        const actions = document.createElement("span");
        actions.className = "order-actions";

        // Тот же контрол, что на «Заказах, ожидающих ответа» — здесь
        // работает как переназначение (заказ уже assigned)
        actions.appendChild(createAssignControl(order));

        appendEditReplaceButtons(actions, order, li);

        const cancelBtn = document.createElement("button");
        cancelBtn.textContent = "Отмена заказа";
        cancelBtn.className = "btn-cancel";
        cancelBtn.addEventListener("click", () => cancelOrder(order.id));
        actions.appendChild(cancelBtn);

        li.appendChild(actions);
        list.appendChild(li);
    });
}

async function refreshAllAssigned() {
    if (!isDispatcherOrAdmin()) return;
    renderAllAssignedOrders(await loadAllAssignedOrders());
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

    document.getElementById("all-assigned-section").hidden = !isDispatcherOrAdmin();

    await refreshQueues();
    await refreshPending();
    await refreshMyOrders();
    await refreshAllAssigned();

    document
        .getElementById("create-order-form")
        .addEventListener("submit", handleCreateOrder);
    document
        .getElementById("route")
        .addEventListener("input", checkRouteLatin);
}

init();
