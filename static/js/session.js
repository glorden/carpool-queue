// Общий виджет "кто я / войти / выйти" — подключается на каждой странице
// сайта (кроме static/link-account.html и static/login-denied.html, у
// которых нет обычной сессии на момент показа). Самостоятельно
// инициализируется при загрузке (как nav.js), результат — в
// window.sessionReady, чтобы страницы, которым нужен currentUser для
// собственной инициализации (dashboard.js, price.js), могли его дождаться
// без повторного запроса.

async function fetchCurrentUser() {
    const res = await fetch("/me");
    const data = await res.json();
    return data.authenticated
        ? { user_id: data.user_id, name: data.name, username: data.username }
        : null;
}

function renderSessionWidget(user) {
    const container = document.getElementById("site-user");
    if (!container) return;
    container.innerHTML = "";

    if (user) {
        const nameSpan = document.createElement("span");
        nameSpan.className = "site-user-name";
        nameSpan.textContent = `Вы: ${user.name}`;

        const logoutBtn = document.createElement("button");
        logoutBtn.type = "button";
        logoutBtn.className = "btn-logout";
        logoutBtn.textContent = "Выйти";
        logoutBtn.addEventListener("click", async () => {
            await fetch("/auth/logout", { method: "POST" });
            window.location.href = "/";
        });

        container.appendChild(nameSpan);
        container.appendChild(logoutBtn);
    } else {
        const loginLink = document.createElement("a");
        loginLink.href = "/auth/vk/login";
        loginLink.className = "btn-vk-login";
        loginLink.textContent = "Войти через VK";
        container.appendChild(loginLink);
    }
}

window.sessionReady = (async function initSession() {
    const user = await fetchCurrentUser();
    renderSessionWidget(user);
    return user;
})();
