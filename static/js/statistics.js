const API_BASE = "";

const OVERVIEW_LABELS = {
    total: "Всего заказов",
    completed: "Завершено",
    active: "Активно",
    cancelled: "Отменено",
};

async function loadStatistics() {
    const res = await fetch(`${API_BASE}/statistics/summary`);
    return await res.json();
}

function renderOverview(overall) {
    const list = document.getElementById("overview-list");
    list.innerHTML = "";

    Object.entries(OVERVIEW_LABELS).forEach(([key, label]) => {
        const li = document.createElement("li");
        li.textContent = `${label}: ${overall[key]}`;
        list.appendChild(li);
    });
}

function renderDriverStats(byDriver) {
    const tbody = document.getElementById("driver-stats-tbody");
    tbody.innerHTML = "";

    if (byDriver.length === 0) {
        const tr = document.createElement("tr");
        tr.className = "empty-row";
        tr.innerHTML = `<td colspan="4">Водителей в очереди нет</td>`;
        tbody.appendChild(tr);
        return;
    }

    byDriver.forEach((driver) => {
        const tr = document.createElement("tr");

        const cells = [
            ["Водитель", driver.name],
            ["Получено", driver.received],
            ["Завершено", driver.completed],
            ["Отменено", driver.cancelled],
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

async function init() {
    const { overall, by_driver } = await loadStatistics();

    renderOverview(overall);
    renderDriverStats(by_driver);
}

init();
