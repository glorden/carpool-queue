const CATEGORY_LABELS = {
    tour: "Туры (туда/обратно + ожидание)",
    direction: "Направления (в одну сторону)",
    business: "Бизнес-класс",
    minivan: "Минивэны",
};

const ACTION_LABELS = {
    created: "добавил(а)",
    updated: "изменил(а)",
    deleted: "удалил(а)",
};

const EDIT_ICON_SVG = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>`;

const DELETE_ICON_SVG = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>`;

function currentUserId() {
    return localStorage.getItem("carpool_user_id");
}

function requireUser() {
    const id = currentUserId();
    if (!id) {
        alert("Сначала выберите себя на Главной");
        return null;
    }
    return Number(id);
}

function normalize(text) {
    return text.toLowerCase().replace(/ё/g, "е").trim();
}

function isPending(priceText) {
    return priceText.toLowerCase().includes("уточн");
}

function formatDate(value) {
    return new Date(value).toLocaleString("ru-RU");
}

async function loadPriceItems() {
    const res = await fetch("/price");
    return res.json();
}

async function loadPriceLog() {
    const res = await fetch("/price/log?limit=50");
    return res.json();
}

function renderItem(item) {
    const li = document.createElement("li");
    li.dataset.id = item.id;
    if (isPending(item.price_text)) {
        li.classList.add("price-pending");
    }

    const row = document.createElement("div");
    row.className = "price-row";

    const nameSpan = document.createElement("span");
    nameSpan.className = "price-name";
    nameSpan.textContent = item.name;
    nameSpan.title = item.name;

    const priceSpan = document.createElement("span");
    priceSpan.className = "price-value";
    priceSpan.textContent = item.price_text;

    const actions = document.createElement("span");
    actions.className = "price-icon-actions";

    const editBtn = document.createElement("button");
    editBtn.type = "button";
    editBtn.className = "icon-btn icon-edit";
    editBtn.setAttribute("aria-label", "Изменить");
    editBtn.title = "Изменить";
    editBtn.innerHTML = EDIT_ICON_SVG;
    editBtn.addEventListener("click", () => startEdit(li, item));

    const deleteBtn = document.createElement("button");
    deleteBtn.type = "button";
    deleteBtn.className = "icon-btn icon-delete";
    deleteBtn.setAttribute("aria-label", "Удалить");
    deleteBtn.title = "Удалить";
    deleteBtn.innerHTML = DELETE_ICON_SVG;
    deleteBtn.addEventListener("click", () => handleDelete(item));

    actions.appendChild(editBtn);
    actions.appendChild(deleteBtn);

    row.appendChild(nameSpan);
    row.appendChild(priceSpan);
    row.appendChild(actions);

    li.appendChild(row);

    return li;
}

function startEdit(li, item) {
    if (!requireUser()) return;

    li.innerHTML = "";
    li.classList.add("price-editing");

    const row = document.createElement("div");
    row.className = "price-row price-row-editing";

    const nameInput = document.createElement("input");
    nameInput.type = "text";
    nameInput.value = item.name;
    nameInput.className = "price-edit-input";

    const priceInput = document.createElement("input");
    priceInput.type = "text";
    priceInput.value = item.price_text;
    priceInput.className = "price-edit-input";

    row.appendChild(nameInput);
    row.appendChild(priceInput);

    const actions = document.createElement("div");
    actions.className = "order-actions";

    const saveBtn = document.createElement("button");
    saveBtn.type = "button";
    saveBtn.textContent = "Сохранить";
    saveBtn.className = "btn-accept";
    saveBtn.addEventListener("click", () =>
        handleSaveEdit(item, nameInput.value, priceInput.value)
    );

    const cancelBtn = document.createElement("button");
    cancelBtn.type = "button";
    cancelBtn.textContent = "Отмена";
    cancelBtn.className = "btn-decline";
    cancelBtn.addEventListener("click", () => refreshAll());

    actions.appendChild(saveBtn);
    actions.appendChild(cancelBtn);

    li.appendChild(row);
    li.appendChild(actions);
}

async function handleSaveEdit(item, name, priceText) {
    const userId = requireUser();
    if (!userId) return;

    name = name.trim();
    priceText = priceText.trim();
    if (!name || !priceText) return;

    try {
        const res = await fetch(`/price/${item.id}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ user_id: userId, name, price_text: priceText }),
        });

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || "Ошибка изменения");
        }

        await refreshAll();
    } catch (e) {
        alert(e.message);
    }
}

async function handleDelete(item) {
    const userId = requireUser();
    if (!userId) return;

    if (!confirm(`Удалить «${item.name}»?`)) return;

    try {
        const res = await fetch(`/price/${item.id}?user_id=${userId}`, {
            method: "DELETE",
        });

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || "Ошибка удаления");
        }

        await refreshAll();
    } catch (e) {
        alert(e.message);
    }
}

async function handleAdd(category, form) {
    const userId = requireUser();
    if (!userId) return;

    const nameInput = form.querySelector(".price-add-name");
    const priceInput = form.querySelector(".price-add-price");

    const name = nameInput.value.trim();
    const priceText = priceInput.value.trim();
    if (!name || !priceText) return;

    try {
        const res = await fetch("/price", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                user_id: userId,
                category,
                name,
                price_text: priceText,
            }),
        });

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || "Ошибка добавления");
        }

        nameInput.value = "";
        priceInput.value = "";
        await refreshAll();
    } catch (e) {
        alert(e.message);
    }
}

function renderPriceItems(items) {
    const byCategory = {};
    items.forEach((item) => {
        if (!byCategory[item.category]) byCategory[item.category] = [];
        byCategory[item.category].push(item);
    });

    Object.keys(CATEGORY_LABELS).forEach((category) => {
        const list = document.getElementById(`price-list-${category}`);
        if (!list) return;
        list.innerHTML = "";
        (byCategory[category] || []).forEach((item) => {
            list.appendChild(renderItem(item));
        });
    });
}

function renderPriceLog(entries) {
    const list = document.getElementById("price-log-list");
    if (!list) return;
    list.innerHTML = "";

    if (entries.length === 0) {
        const li = document.createElement("li");
        li.textContent = "Изменений пока не было";
        list.appendChild(li);
        return;
    }

    entries.forEach((entry) => {
        const li = document.createElement("li");
        const who = entry.user_name || `#${entry.user_id}`;
        const actionLabel = ACTION_LABELS[entry.action] || entry.action;

        let detail = `«${entry.item_name}»`;
        if (entry.action === "updated") {
            detail += `: ${entry.old_value} → ${entry.new_value}`;
        } else if (entry.action === "created") {
            detail += `: ${entry.new_value}`;
        } else if (entry.action === "deleted") {
            detail += `: ${entry.old_value}`;
        }

        li.textContent = `${who} ${actionLabel} ${detail} — ${formatDate(entry.created_at)}`;
        list.appendChild(li);
    });
}

function reapplySearch() {
    const input = document.getElementById("price-search");
    if (input && input.value) {
        input.dispatchEvent(new Event("input"));
    }
}

async function refreshAll() {
    const items = await loadPriceItems();
    renderPriceItems(items);
    reapplySearch();

    const log = await loadPriceLog();
    renderPriceLog(log);
}

function initAddForms() {
    document.querySelectorAll(".price-add-form").forEach((form) => {
        form.addEventListener("submit", (event) => {
            event.preventDefault();
            handleAdd(form.dataset.category, form);
        });
    });
}

function initPriceSearch() {
    const input = document.getElementById("price-search");
    const noResults = document.getElementById("price-no-results");
    if (!input) return;

    input.addEventListener("input", () => {
        const query = normalize(input.value);

        const items = Array.from(document.querySelectorAll(".price-list li"));
        items.forEach((li) => {
            const nameSpan = li.querySelector(".price-name");
            const name = nameSpan ? normalize(nameSpan.textContent) : "";
            li.style.display = query === "" || name.includes(query) ? "" : "none";
        });

        const lists = Array.from(document.querySelectorAll(".price-list"));
        lists.forEach((ul) => {
            const hasVisibleItem = Array.from(ul.children).some(
                (li) => li.style.display !== "none"
            );
            ul.style.display = hasVisibleItem ? "" : "none";
        });

        const sections = Array.from(document.querySelectorAll(".price-section"));
        sections.forEach((section) => {
            const hasVisibleList = Array.from(
                section.querySelectorAll(".price-list")
            ).some((ul) => ul.style.display !== "none");
            section.style.display = hasVisibleList ? "" : "none";
        });

        if (noResults) {
            const anyVisible = sections.some((s) => s.style.display !== "none");
            noResults.style.display = anyVisible ? "none" : "";
        }
    });
}

async function init() {
    initAddForms();
    initPriceSearch();
    await refreshAll();
}

init();
