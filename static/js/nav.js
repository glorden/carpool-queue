const SITE_PAGES = [
    { href: "/", label: "Главная" },
    { href: "/static/price.html", label: "Прайс" },
    { href: "/static/history.html", label: "История заказов" },
    { href: "/static/activity.html", label: "Журнал действий" },
    { href: "/static/statistics.html", label: "Статистика" },
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
