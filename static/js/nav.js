const SITE_PAGES = [
    { href: "/", label: "Дэшборд" },
    { href: "/static/history.html", label: "История заказов" },
    { href: "/static/price.html", label: "Прайс" },
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
