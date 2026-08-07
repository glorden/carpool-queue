// Кнопка «Установить на экран» — общий элемент каркаса (см. STYLEGUIDE.md),
// подключается на каждой полноценной странице. Устанавливает именно ту
// страницу, на которой находится пользователь — браузер сам берёт манифест,
// подключённый через <link rel="manifest"> текущей страницы (index.html и
// большинство страниц → site.webmanifest «Очередь», price.html → отдельный
// price.webmanifest «Прайс», см. ARCHITECTURE.md, «PWA»).
//
// Android/desktop Chrome, Edge — настоящая установка через
// beforeinstallprompt. iOS Safari это событие принципиально не поддерживает
// (Apple не даёт запускать установку программно) — вместо кнопки показываем
// статичную подсказку с инструкцией через Share.

function isStandalone() {
    return (
        window.matchMedia("(display-mode: standalone)").matches ||
        window.navigator.standalone === true
    );
}

function isIos() {
    return /iphone|ipad|ipod/i.test(window.navigator.userAgent);
}

function renderInstallButton(promptEvent) {
    const container = document.getElementById("install-prompt");
    if (!container) return;

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn-install";
    btn.textContent = "Установить на экран";
    btn.addEventListener("click", async () => {
        promptEvent.prompt();
        await promptEvent.userChoice;
        container.hidden = true; // событие одноразовое в любом случае
    });

    container.innerHTML = "";
    container.appendChild(btn);
    container.hidden = false;
}

function renderIosHint() {
    const container = document.getElementById("install-prompt");
    if (!container) return;

    const hint = document.createElement("p");
    hint.className = "install-hint";
    hint.textContent =
        "Чтобы установить на экран: нажмите ↑ «Поделиться» внизу экрана и выберите «На экран «Домой»».";

    container.innerHTML = "";
    container.appendChild(hint);
    container.hidden = false;
}

if (!isStandalone()) {
    window.addEventListener("beforeinstallprompt", (event) => {
        event.preventDefault();
        renderInstallButton(event);
    });

    window.addEventListener("appinstalled", () => {
        const container = document.getElementById("install-prompt");
        if (container) container.hidden = true;
    });

    if (isIos()) {
        renderIosHint();
    }
}
