# Стайлгайд для страниц сайта

Короткий свод соглашений, чтобы новые страницы не расходились по стилю
со старыми. Без фреймворков и шаблонизаторов (см. ARCHITECTURE.md) —
единообразие держится на общих файлах (`style.css`, `nav.js`) и этих
правилах.

## Обязательный каркас страницы

Каждая HTML-страница в `static/` начинается одинаково:

```html
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>...</title>
    <link rel="icon" type="image/png" sizes="32x32" href="/static/fav/favicon-32x32.png">
    <link rel="icon" type="image/png" sizes="16x16" href="/static/fav/favicon-16x16.png">
    <link rel="apple-touch-icon" sizes="180x180" href="/static/fav/apple-touch-icon.png">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-title" content="...">
    <link rel="icon" href="/static/fav/favicon.ico">
    <link rel="manifest" href="/static/fav/site.webmanifest">
    <link rel="stylesheet" href="/static/css/style.css">
</head>
<body>
    <header>
        <h1>...</h1>
    </header>

    <div id="site-user" class="site-user"></div>

    <nav id="site-nav" class="site-nav"></nav>

    <div id="install-prompt" class="install-prompt" hidden></div>

    <main>
        ...
    </main>

    <script src="/static/js/nav.js"></script>
    <script src="/static/js/session.js"></script>
    <script src="/static/js/install.js"></script>
    <!-- страница-специфичный JS, если есть -->
</body>
</html>
```

- `viewport` и `favicon` — обязательны, без исключений.
- `<title>` — то же самое, что текст `<h1>` страницы, без префикса
  «Carpool Queue» — заголовок вкладки браузера короткий и однозначный.
- `apple-mobile-web-app-title` — название под иконкой при установке через
  iOS Safari, не берётся из manifest (см. ARCHITECTURE.md, «PWA»). Как
  правило совпадает с `<title>`/`<h1>` страницы — «Очередь» везде, кроме
  `price.html` («Прайс»).
- Навигация между страницами — только через `<nav id="site-nav">` +
  `nav.js`. Список страниц редактируется в одном месте —
  `static/js/nav.js` (`SITE_PAGES`). Никаких ссылок на другие страницы
  нигде больше не хардкодим.
- Вход через VK — только через `<div id="site-user">` + `session.js`
  (кнопка «Войти через VK» или «Вы: Имя» + «Выйти», см. ARCHITECTURE.md,
  «Вход через VK ID»). Как и с навигацией — общий элемент каркаса, а не
  часть конкретной страницы.
- Кнопка «Установить на экран» — только через `<div id="install-prompt">`
  + `install.js` (см. ARCHITECTURE.md, «PWA»). Тот же принцип: общий
  элемент каркаса, конкретные страницы его не наполняют сами.
- `<header>` содержит только заголовок страницы и то, что относится
  конкретно к ней. Общие для всех страниц элементы (навигация, вход,
  установка) в `<header>` не живут.
- `<link rel="manifest">` — `site.webmanifest` («Очередь») везде, кроме
  `price.html`, у которой свой `price.webmanifest` («Прайс») — так
  пользователь может установить Прайс на домашний экран отдельным
  значком, не переустанавливая весь сайт (см. ARCHITECTURE.md, «PWA»).
  Если когда-нибудь понадобится собственный значок ещё одной странице —
  тот же приём: свой `.webmanifest` со своим `id`/`start_url`, `scope`
  оставить `"/"`.
- Исключение из каркаса — `static/link-account.html` (экран самопривязки
  VK-аккаунта) и `static/login-denied.html` (отказ во входе): у них ещё/уже
  нет обычной сессии на момент показа, поэтому без `<nav>`/`session.js`/
  `install.js`, только общий `style.css`, favicon и apple-mobile-web-app-*
  для визуальной консистентности.

## Мобильный подход

Сайт используется в основном с телефона — проектируем от мобильного,
не наоборот.

- Брейкпоинт для переверстки под мобильный: `640px`
  (см. `@media (max-width: 640px)` в `style.css`).
- Инпуты — `font-size: 16px` (меньше вызывает автозум на iOS Safari).
- Кликабельные элементы (кнопки) — `min-height: 40–44px` (палец, не
  курсор).
- Широкие таблицы на мобильном не скроллим вбок — превращаем строки в
  карточки (`data-label` + `::before`, см. `#history-table` в
  `style.css`) или используем изначально верстку без таблиц (списки
  `<ul>`/`<li>`, как в `price.html`).
- Проверяем на 375px ширине (iPhone SE/стандартный мобильный), что нет
  горизонтального переполнения (`document.body.scrollWidth <=
  window.innerWidth`).

## Цвета

| Назначение | Цвет |
|---|---|
| Текст | `#222` |
| Ссылки / основной акцент | `#37c` |
| Успех / принято | `#0a7` |
| Ошибка / отклонено | `#c33` |
| Второстепенный текст (подписи, текущая страница в nav) | `#888` / `#666` |
| Разделители | `#eee` / `#ddd` / `#f0f0f0` |

## Прочее

- `* { box-sizing: border-box; }` уже задано глобально — не переопределять.
- `body { max-width: 700px; margin: 0 auto; }` — единая ширина контента
  на всех страницах.
- Один общий `static/css/style.css` на все страницы, отдельных
  стилей под конкретную страницу не заводим (если стиль нужен только
  одной странице — это нормально, просто в общем файле с явным
  комментарием/селектором по `id` страницы).
- `static/js/nav.js` регистрирует service worker (`static/sw.js`, см.
  ARCHITECTURE.md, «PWA») — это тоже часть общего каркаса, не трогать
  отдельно в каждом HTML-файле. Кэш статики самообновляется в фоне
  (stale-while-revalidate) — руками `CACHE_NAME` в `static/sw.js`
  бампать не обязательно, но можно, если хочется принудительно сбросить
  весь кэш разом (например, если что-то подозрительно закэшировалось).
