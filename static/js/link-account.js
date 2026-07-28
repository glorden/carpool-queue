async function loadCandidates() {
    const res = await fetch("/auth/vk/link-candidates");
    if (!res.ok) {
        document.getElementById("link-candidates-list").textContent =
            "Сессия для привязки не найдена или уже истекла. Начните вход заново.";
        return null;
    }
    return res.json();
}

function renderCandidates(candidates) {
    const list = document.getElementById("link-candidates-list");
    list.innerHTML = "";

    if (candidates.length === 0) {
        list.textContent = "Свободных пользователей для привязки не осталось. Обратитесь к администратору.";
        return;
    }

    candidates.forEach((candidate) => {
        const li = document.createElement("li");

        const nameSpan = document.createElement("span");
        nameSpan.textContent = candidate.name;

        const button = document.createElement("button");
        button.type = "button";
        button.textContent = "Это я";
        button.addEventListener("click", () => confirmLink(candidate));

        li.appendChild(nameSpan);
        li.appendChild(button);
        list.appendChild(li);
    });
}

async function confirmLink(candidate) {
    const confirmed = confirm(
        `Подтвердите: вы — ${candidate.name}? Отменить это на сайте будет нельзя.`
    );
    if (!confirmed) {
        return;
    }

    try {
        const res = await fetch("/auth/vk/link", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ user_id: candidate.user_id }),
        });

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || "Не удалось привязать аккаунт");
        }

        window.location.href = "/";
    } catch (e) {
        alert(e.message);
    }
}

async function init() {
    const candidates = await loadCandidates();
    if (candidates) {
        renderCandidates(candidates);
    }
}

init();
