const API_BASE = "";

function formatDate(value) {
    if (!value) return "—";

    const d = new Date(value);
    return d.toLocaleString("ru-RU");
}

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

async function loadActivity(userId, eventType) {
    const params = new URLSearchParams();

    if (userId) params.set("user_id", userId);
    if (eventType) params.set("event_type", eventType);
    params.set("limit", "200");

    const res = await fetch(`${API_BASE}/activity?${params.toString()}`);
    return await res.json();
}

function renderActivity(entries) {
    const list = document.getElementById("activity-list");
    list.innerHTML = "";

    if (entries.length === 0) {
        const li = document.createElement("li");
        li.textContent = "Событий не найдено";
        list.appendChild(li);
        return;
    }

    entries.forEach((entry) => {
        const li = document.createElement("li");
        li.textContent = `${formatDate(entry.created_at)} — ${entry.message}`;
        list.appendChild(li);
    });
}

async function applyFilters(users) {
    const userId = document.getElementById("filter-user").value;
    const eventType = document.getElementById("filter-event-type").value;

    const entries = await loadActivity(userId, eventType);

    renderActivity(entries);
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
