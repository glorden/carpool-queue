const QUEUE_TYPES = ["long", "short"];

let currentUser = null;
let usersCache = [];
let queueCache = { long: [], short: [] };

function updateAuthGate() {
    const authed = !!currentUser;
    document.getElementById("auth-gated").hidden = !authed;
    document.getElementById("login-prompt").hidden = authed;

    if (authed) {
        const isAdmin = !!currentUser.is_admin;
        document.getElementById("admin-content").hidden = !isAdmin;
        document.getElementById("admin-forbidden").hidden = isAdmin;
    }
}

async function loadUsers() {
    const res = await fetch("/users");
    return res.json();
}

async function loadQueue(queueType) {
    const res = await fetch(`/queue?queue_type=${queueType}`);
    return res.json();
}

async function refreshAll() {
    usersCache = await loadUsers();
    renderRolesList(usersCache);

    for (const queueType of QUEUE_TYPES) {
        queueCache[queueType] = await loadQueue(queueType);
        renderQueueList(queueType);
        renderAddToQueueSelect(queueType);
    }
}

// --- Пользователи и роли ---

function renderRolesList(users) {
    const list = document.getElementById("roles-list");
    list.innerHTML = "";

    if (users.length === 0) {
        const li = document.createElement("li");
        li.textContent = "Пользователей пока нет";
        list.appendChild(li);
        return;
    }

    users.forEach((user) => {
        const li = document.createElement("li");

        const nameSpan = document.createElement("span");
        nameSpan.className = "users-list-name";
        nameSpan.textContent = user.name;
        li.appendChild(nameSpan);

        const rolesSpan = document.createElement("span");
        rolesSpan.className = "admin-roles-row";

        [
            ["is_driver", "Водитель"],
            ["is_dispatcher", "Диспетчер"],
            ["is_admin", "Администратор"],
        ].forEach(([field, label]) => {
            const roleLabel = document.createElement("label");
            roleLabel.className = "checkbox-label";

            const checkbox = document.createElement("input");
            checkbox.type = "checkbox";
            checkbox.checked = !!user[field];
            checkbox.addEventListener("change", () =>
                updateUserRole(user.user_id, field, checkbox.checked)
            );

            roleLabel.appendChild(checkbox);
            roleLabel.appendChild(document.createTextNode(label));
            rolesSpan.appendChild(roleLabel);
        });

        li.appendChild(rolesSpan);
        list.appendChild(li);
    });
}

async function updateUserRole(userId, field, value) {
    try {
        const res = await fetch(`/admin/users/${userId}/roles`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ [field]: value }),
        });

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || "Ошибка изменения роли");
        }

        await refreshAll();
    } catch (e) {
        alert(e.message);
        await refreshAll(); // вернуть чекбокс в состояние, соответствующее серверу
    }
}

// --- Добавление пользователя ---

async function handleAddUser(event) {
    event.preventDefault();

    const statusEl = document.getElementById("add-user-status");
    statusEl.classList.remove("error");

    const name = document.getElementById("new-user-name").value.trim();
    const username = document.getElementById("new-user-username").value.trim();
    const isDriver = document.getElementById("new-user-is-driver").checked;
    const isDispatcher = document.getElementById("new-user-is-dispatcher").checked;
    const isAdmin = document.getElementById("new-user-is-admin").checked;
    const queueTypes = [];
    if (document.getElementById("new-user-queue-long").checked) queueTypes.push("long");
    if (document.getElementById("new-user-queue-short").checked) queueTypes.push("short");

    if (!name || !username) return;

    statusEl.textContent = "Добавляю...";

    try {
        const res = await fetch("/admin/users", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                name,
                username,
                is_driver: isDriver,
                is_dispatcher: isDispatcher,
                is_admin: isAdmin,
                queue_types: queueTypes,
            }),
        });

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || "Ошибка добавления пользователя");
        }

        statusEl.textContent = `Добавлен: ${name}`;
        document.getElementById("add-user-form").reset();
        await refreshAll();
    } catch (e) {
        statusEl.textContent = e.message;
        statusEl.classList.add("error");
    }
}

// --- Порядок очереди ---

function renderQueueList(queueType) {
    const list = document.getElementById(`admin-queue-${queueType}`);
    const queue = queueCache[queueType];
    list.innerHTML = "";

    if (queue.length === 0) {
        const li = document.createElement("li");
        li.textContent = "Очередь пуста";
        list.appendChild(li);
        return;
    }

    queue.forEach((entry, index) => {
        const li = document.createElement("li");
        li.className = "admin-queue-row";

        const nameSpan = document.createElement("span");
        nameSpan.className = "admin-queue-name";
        nameSpan.textContent = entry.name;
        li.appendChild(nameSpan);

        const actions = document.createElement("span");
        actions.className = "admin-queue-actions";

        const upBtn = document.createElement("button");
        upBtn.type = "button";
        upBtn.textContent = "▲";
        upBtn.setAttribute("aria-label", "Выше");
        upBtn.disabled = index === 0;
        upBtn.addEventListener("click", () => moveInQueue(queueType, index, -1));

        const downBtn = document.createElement("button");
        downBtn.type = "button";
        downBtn.textContent = "▼";
        downBtn.setAttribute("aria-label", "Ниже");
        downBtn.disabled = index === queue.length - 1;
        downBtn.addEventListener("click", () => moveInQueue(queueType, index, 1));

        const removeBtn = document.createElement("button");
        removeBtn.type = "button";
        removeBtn.textContent = "✕";
        removeBtn.setAttribute("aria-label", "Убрать из очереди");
        removeBtn.className = "btn-queue-remove";
        removeBtn.addEventListener("click", () => removeFromQueue(queueType, entry.user_id));

        actions.appendChild(upBtn);
        actions.appendChild(downBtn);
        actions.appendChild(removeBtn);
        li.appendChild(actions);

        list.appendChild(li);
    });
}

async function moveInQueue(queueType, index, delta) {
    const queue = queueCache[queueType];
    const newIndex = index + delta;
    if (newIndex < 0 || newIndex >= queue.length) return;

    const reordered = queue.slice();
    [reordered[index], reordered[newIndex]] = [reordered[newIndex], reordered[index]];

    await submitReorder(queueType, reordered.map((entry) => entry.user_id));
}

async function submitReorder(queueType, userIds) {
    try {
        const res = await fetch(`/admin/queue/${queueType}/reorder`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ user_ids: userIds }),
        });

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || "Ошибка перестановки очереди");
        }

        queueCache[queueType] = await loadQueue(queueType);
        renderQueueList(queueType);
    } catch (e) {
        alert(e.message);
    }
}

async function removeFromQueue(queueType, userId) {
    if (!confirm("Убрать из очереди?")) return;

    try {
        const res = await fetch(`/admin/users/${userId}/queue/${queueType}`, {
            method: "DELETE",
        });

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || "Ошибка удаления из очереди");
        }

        queueCache[queueType] = await loadQueue(queueType);
        renderQueueList(queueType);
        renderAddToQueueSelect(queueType);
    } catch (e) {
        alert(e.message);
    }
}

function renderAddToQueueSelect(queueType) {
    const select = document.getElementById(`admin-queue-add-select-${queueType}`);
    select.innerHTML = "";

    const inQueueIds = new Set(queueCache[queueType].map((entry) => entry.user_id));
    const candidates = usersCache.filter(
        (user) => user.is_driver && !inQueueIds.has(user.user_id)
    );

    if (candidates.length === 0) {
        const option = document.createElement("option");
        option.textContent = "Некого добавить";
        option.disabled = true;
        select.appendChild(option);
        select.disabled = true;
        return;
    }

    select.disabled = false;
    candidates.forEach((user) => {
        const option = document.createElement("option");
        option.value = user.user_id;
        option.textContent = user.name;
        select.appendChild(option);
    });
}

async function handleAddToQueue(queueType) {
    const select = document.getElementById(`admin-queue-add-select-${queueType}`);
    if (!select.value) return;

    try {
        const res = await fetch(`/admin/users/${select.value}/queue/${queueType}`, {
            method: "POST",
        });

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || "Ошибка добавления в очередь");
        }

        queueCache[queueType] = await loadQueue(queueType);
        renderQueueList(queueType);
        renderAddToQueueSelect(queueType);
    } catch (e) {
        alert(e.message);
    }
}

async function init() {
    currentUser = await window.sessionReady;
    updateAuthGate();
    if (!currentUser || !currentUser.is_admin) return;

    document.getElementById("add-user-form").addEventListener("submit", handleAddUser);
    document.querySelectorAll(".btn-admin-queue-add").forEach((btn) => {
        btn.addEventListener("click", () => handleAddToQueue(btn.dataset.queueType));
    });

    await refreshAll();
}

init();
