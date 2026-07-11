const API_BASE = "";

async function loadUsers() {
    const res = await fetch(`${API_BASE}/queue`);
    return await res.json();
}

function populateUserFilter(users) {
    const select = document.getElementById("filter-user");
    users.forEach((entry) => {
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

async function loadOrders(status, userId) {
    const params = new URLSearchParams();
    if (status) params.set("status", status);
    if (userId) params.set("user_id", userId);

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
        tr.innerHTML = `<td colspan="7">Заказов не найдено</td>`;
        tbody.appendChild(tr);
        return;
    }

    const userMap = {};
    users.forEach((u) => {
        userMap[u.user_id] = u.name;
    });

    orders.forEach((order) => {
        const tr = document.createElement("tr");
        const executorName = order.assigned_to
            ? userMap[order.assigned_to] || `#${order.assigned_to}`
            : "—";

        tr.innerHTML = `
            <td>${order.id}</td>
            <td>${order.route || "—"}</td>
            <td>${order.comment || "—"}</td>
            <td>${order.status}</td>
            <td>${executorName}</td>
            <td>${formatDate(order.created_at)}</td>
            <td>${formatDate(order.completed_at)}</td>
        `;
        tbody.appendChild(tr);
    });
}

async function applyFilters(users) {
    const status = document.getElementById("filter-status").value;
    const userId = document.getElementById("filter-user").value;
    const orders = await loadOrders(status, userId);
    renderOrders(orders, users);
}

async function init() {
    const users = await loadUsers();
    populateUserFilter(users);

    await applyFilters(users);

    document
        .getElementById("apply-filters")
        .addEventListener("click", () => applyFilters(users));
}

init();