const SITE_PAGES = [
    { href: "/", label: "Главная" },
    { href: "/static/price.html", label: "Прайс" },
    { href: "/static/history.html", label: "История заказов" },
    { href: "/static/activity.html", label: "Журнал действий" },
    { href: "/static/statistics.html", label: "Статистика" },
    { href: "/static/users.html", label: "Пользователи" },
];

function renderSiteNav() {
    const container = document.getElementById("site-nav");
    if (!container) return;

    const currentPath = window.location.pathname;

    container.innerHTML = SITE_PAGES.map((page) => {
        const isCurrent =
            page.href === currentPath ||
            (page.href === "/" && currentPath === "/static/index.html");

        return isCurrent
            ? `<span class="site-nav-current">${page.label}</span>`
            : `<a href="${page.href}">${page.label}</a>`;
    }).join("");
}

renderSiteNav();

// «Админ» — не в статичном SITE_PAGES: добавляется вторым проходом, только
// когда известно, что текущий пользователь администратор. К моменту
// DOMContentLoaded все синхронные <script> (в т.ч. session.js, который
// создаёт window.sessionReady) уже выполнены, гонки не будет.
document.addEventListener("DOMContentLoaded", () => {
    if (!window.sessionReady) return;

    window.sessionReady.then((user) => {
        if (!user || !user.is_admin) return;
        if (SITE_PAGES.some((page) => page.href === "/static/admin.html")) return;

        SITE_PAGES.push({ href: "/static/admin.html", label: "Админ" });
        renderSiteNav();
    });
});

// PWA: регистрация service worker'а (устанавливаемость на домашний экран,
// см. ARCHITECTURE.md, «PWA»). /sw.js — не /static/sw.js, чтобы scope по
// умолчанию покрывал весь сайт (см. app/main.py, service_worker()).
if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => {
        navigator.serviceWorker.register("/sw.js").catch((err) => {
            console.warn("Service worker registration failed:", err);
        });
    });
}
