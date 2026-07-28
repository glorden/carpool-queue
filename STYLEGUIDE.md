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

    <main>
        ...
    </main>

    <script src="/static/js/nav.js"></script>
    <script src="/static/js/session.js"></script>
    <!-- страница-специфичный JS, если есть -->
</body>
</html>
```

- `viewport` и `favicon` — обязательны, без исключений.
- Навигация между страницами — только через `<nav id="site-nav">` +
  `nav.js`. Список страниц редактируется в одном месте —
  `static/js/nav.js` (`SITE_PAGES`). Никаких ссылок на другие страницы
  нигде больше не хардкодим.
- Вход через VK — только через `<div id="site-user">` + `session.js`
  (кнопка «Войти через VK» или «Вы: Имя» + «Выйти», см. ARCHITECTURE.md,
  «Вход через VK ID»). Как и с навигацией — общий элемент каркаса, а не
  часть конкретной страницы.
- `<header>` содержит только заголовок страницы и то, что относится
  конкретно к ней. Общие для всех страниц элементы (навигация, вход)
  в `<header>` не живут.
- Исключение из каркаса — `static/link-account.html` (экран самопривязки
  VK-аккаунта) и `static/login-denied.html` (отказ во входе): у них ещё/уже
  нет обычной сессии на момент показа, поэтому без `<nav>`/`session.js`,
  только общий `style.css` и favicon для визуальной консистентности.

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
