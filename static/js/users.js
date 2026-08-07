const ROLE_LABELS = {
    is_driver: "Водитель",
    is_dispatcher: "Диспетчер",
    is_admin: "Администратор",
};

const ROLE_TAG_CLASSES = {
    is_driver: "role-tag-driver",
    is_dispatcher: "role-tag-dispatcher",
    is_admin: "role-tag-admin",
};

// Порядок отображения ролей везде: администратор → диспетчер → водитель.
const ROLE_ORDER = ["is_admin", "is_dispatcher", "is_driver"];

let currentUser = null;

function highestRoleRank(user) {
    const rank = ROLE_ORDER.findIndex((roleKey) => user[roleKey]);
    return rank === -1 ? ROLE_ORDER.length : rank;
}

function sortUsersByRole(users) {
    return [...users].sort((a, b) => highestRoleRank(a) - highestRoleRank(b));
}

function updateAuthGate() {
    document.getElementById("auth-gated").hidden = !currentUser;
    document.getElementById("login-prompt").hidden = !!currentUser;
}

async function loadUsers() {
    const res = await fetch("/users");
    return res.json();
}

function createRoleTag(roleKey) {
    const span = document.createElement("span");
    span.className = `role-tag ${ROLE_TAG_CLASSES[roleKey]}`;
    span.textContent = ROLE_LABELS[roleKey];
    return span;
}

function renderUsers(users) {
    const list = document.getElementById("users-list");
    list.innerHTML = "";
    users = sortUsersByRole(users);

    if (users.length === 0) {
        const li = document.createElement("li");
        li.textContent = "Пользователей пока нет";
        list.appendChild(li);
        return;
    }

    users.forEach((user) => {
        const li = document.createElement("li");

        const nameSpan = document.createElement("span");
        nameSpan.className = "users-list-name";
        nameSpan.textContent = user.name;
        li.appendChild(nameSpan);

        const roles = document.createElement("span");
        roles.className = "users-list-roles";
        ROLE_ORDER
            .filter((roleKey) => user[roleKey])
            .forEach((roleKey) => roles.appendChild(createRoleTag(roleKey)));

        if (!roles.children.length) {
            const noRole = document.createElement("span");
            noRole.className = "users-list-no-role";
            noRole.textContent = "без роли";
            roles.appendChild(noRole);
        }

        li.appendChild(roles);
        list.appendChild(li);
    });
}

async function init() {
    currentUser = await window.sessionReady;
    updateAuthGate();
    if (!currentUser) return;

    renderUsers(await loadUsers());
}

init();
