const API_BASE = "";

const STATUS_LABELS = {
    pending: "Ожидает",
    assigned: "Назначен",
    completed: "Завершён",
    cancelled: "Отменён",
};

const QUEUE_TYPE_LABELS = {
    long: "Дальний",
    short: "Короткий",
};

async function loadUsers() {
    const res = await fetch(`${API_BASE}/queue`);
    return await res.json();
}

function populateUserFilter(users) {
    const select = document.getElementById("filter-user");
    const seen = new Set();

    users.forEach((entry) => {
        // /queue без queue_type отдаёт обе очереди — пользователь,
        // состоящий в обеих, попал бы в фильтр дважды
        if (seen.has(entry.user_id)) return;
        seen.add(entry.user_id);

        const option = document.createElement("option");
        option.value = entry.user_id;
        option.textContent = entry.name;
        select.appendChild(option);
    });
}

function formatDate(value) {
    if (!value) return "—";

    const d = new Date(value);
    return d.toLocaleString("ru-RU");
}

async function loadOrders(status, userId, queueType) {
    const params = new URLSearchParams();

    if (status) params.set("status", status);
    if (userId) params.set("user_id", userId);
    if (queueType) params.set("queue_type", queueType);

    const query = params.toString();
    const url = query ? `${API_BASE}/orders?${query}` : `${API_BASE}/orders`;

    const res = await fetch(url);
    return await res.json();
}

function renderOrders(orders, users) {
    const tbody = document.getElementById("history-tbody");
    tbody.innerHTML = "";

    if (orders.length === 0) {
        const tr = document.createElement("tr");
        tr.className = "empty-row";
        tr.innerHTML = `<td colspan="9">Заказы не найдены</td>`;
        tbody.appendChild(tr);
        return;
    }

    const userMap = {};

    users.forEach((u) => {
        userMap[u.user_id] = u.name;
    });

    orders.forEach((order) => {
        const tr = document.createElement("tr");

        const driverName = order.assigned_to
            ? userMap[order.assigned_to] || `#${order.assigned_to}`
            : "—";

        const cells = [
            ["ID", order.id],
            ["Тип", QUEUE_TYPE_LABELS[order.queue_type] || order.queue_type],
            ["Маршрут", order.route || "—"],
            ["Комментарий", order.comment || "—"],
            ["Статус", STATUS_LABELS[order.status] || order.status],
            ["Водитель", driverName],
            ["Создан", formatDate(order.created_at)],
            ["Завершён", formatDate(order.completed_at)],
            ["Причина самоназначения", order.self_assign_reason || "—"],
        ];

        cells.forEach(([label, value]) => {
            const td = document.createElement("td");
            td.dataset.label = label;
            td.textContent = value;
            tr.appendChild(td);
        });

        tbody.appendChild(tr);
    });
}

async function applyFilters(users) {
    const status = document.getElementById("filter-status").value;
    const userId = document.getElementById("filter-user").value;
    const queueType = document.getElementById("filter-queue-type").value;

    const orders = await loadOrders(status, userId, queueType);

    renderOrders(orders, users);
}

let currentUser = null;

function updateAuthGate() {
    document.getElementById("auth-gated").hidden = !currentUser;
    document.getElementById("login-prompt").hidden = !!currentUser;
}

async function init() {
    currentUser = await window.sessionReady;
    updateAuthGate();
    if (!currentUser) return;

    const users = await loadUsers();

    populateUserFilter(users);

    await applyFilters(users);

    document
        .getElementById("apply-filters")
        .addEventListener("click", () => applyFilters(users));
}

init();