// Service worker для установки сайта на домашний экран (PWA). Кэширует
// ТОЛЬКО статику (css/js/fav) — HTML-страницы и все API-запросы всегда
// идут через сеть. Очередь и заказы — живые операционные данные, показать
// водителю устаревшую офлайн-копию (кто первый, какой заказ ещё pending)
// реально опасно для бизнеса, а не просто неудобно (см. ARCHITECTURE.md,
// «PWA»).
//
// Стратегия — stale-while-revalidate, не чистый cache-first (был им до
// 0.4.2): отдаём закэшированный файл сразу, если он есть, но параллельно
// всегда идём в сеть и обновляем кэш для следующего раза. Чистый
// cache-first без этого требовал вручную бампать CACHE_NAME при каждом
// изменении style.css/*.js — на практике это один раз забыли сделать
// (0.4.1) и пользователь застрял на старой версии session.js на
// обычной навигации по ссылкам (Ctrl+F5 помогал — он обходит service
// worker целиком, это поведение браузера, не этого кода). Теперь
// свежая версия подхватывается сама, максимум через одну лишнюю
// загрузку — без ручных версий вообще.
const CACHE_NAME = "carpool-static-v2";
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

            const revalidate = fetch(request)
                .then((response) => {
                    if (response.ok) cache.put(request, response.clone());
                    return response;
                })
                .catch(() => null);

            // Без waitUntil браузер может прибить воркер сразу после того,
            // как respondWith() получит cached — фоновое обновление кэша
            // до сети может не доехать
            event.waitUntil(revalidate);

            if (cached) return cached;
            return (await revalidate) || Response.error();
        })
    );
});
