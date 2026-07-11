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

async function init() {
    currentQueue = await loadQueue();
    populateUserSelector(currentQueue);
    renderQueue(currentQueue);
}

init();