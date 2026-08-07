// Service worker для установки сайта на домашний экран (PWA). Кэширует
// ТОЛЬКО статику (css/js/fav) — HTML-страницы и все API-запросы всегда
// идут через сеть. Очередь и заказы — живые операционные данные, показать
// водителю устаревшую офлайн-копию (кто первый, какой заказ ещё pending)
// реально опасно для бизнеса, а не просто неудобно (см. ARCHITECTURE.md,
// «PWA»). Бампать CACHE_NAME при следующем изменении style.css/*.js —
// иначе вернувшийся пользователь может залипнуть на старой статике.
const CACHE_NAME = "carpool-static-v1";
const STATIC_PREFIXES = ["/static/css/", "/static/js/", "/static/fav/"];

function isCacheableStatic(url) {
    const path = new URL(url).pathname;
    return STATIC_PREFIXES.some((prefix) => path.startsWith(prefix));
}

self.addEventListener("install", () => {
    self.skipWaiting();
});

self.addEventListener("activate", (event) => {
    event.waitUntil(
        caches
            .keys()
            .then((names) =>
                Promise.all(
                    names.filter((name) => name !== CACHE_NAME).map((name) => caches.delete(name))
                )
            )
            .then(() => self.clients.claim())
    );
});

self.addEventListener("fetch", (event) => {
    const { request } = event;

    if (request.method !== "GET" || !isCacheableStatic(request.url)) {
        return; // HTML/API — не вмешиваемся, обычный сетевой запрос
    }

    event.respondWith(
        caches.open(CACHE_NAME).then(async (cache) => {
            const cached = await cache.match(request);
            if (cached) return cached;

            const response = await fetch(request);
            if (response.ok) {
                cache.put(request, response.clone());
            }
            return response;
        })
    );
});
