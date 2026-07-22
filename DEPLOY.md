# Деплой на VPS (Шаг 11)

Инструкция по развёртыванию Carpool Queue на чистом Ubuntu Server.
Актуальна для боевого сервера (Ubuntu 24.04 LTS, Caddy, systemd),
задеплоенного 2026-07-22 на `zakaz.glorden.ru`.

## Требования к серверу

- Ubuntu 22.04/24.04 LTS, root-доступ по SSH
- Домен/поддомен с A-записью, указывающей на IP сервера
  (для автоматического HTTPS через Caddy)
- Минимум 1 vCPU / 1GB RAM — этого достаточно для FastAPI + SQLite
  на группу ~10 человек

## Установка с нуля

### 1. Обновление системы и базовые пакеты
```bash
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get -o Dpkg::Options::='--force-confold' upgrade -y
apt-get autoremove -y
apt-get install -y python3-venv python3-pip git ufw curl
```
Если после этого существует `/var/run/reboot-required` — перезагрузить
сервер (`reboot`) и переподключиться.

### 2. Отдельный пользователь для сервиса (без root)
```bash
adduser --disabled-password --gecos "" deploy
mkdir -p /home/deploy/.ssh
cp ~/.ssh/authorized_keys /home/deploy/.ssh/authorized_keys
chown -R deploy:deploy /home/deploy/.ssh
chmod 700 /home/deploy/.ssh && chmod 600 /home/deploy/.ssh/authorized_keys
```

### 3. Установка Caddy
```bash
apt-get install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
apt-get update -y
apt-get install -y caddy
```

### 4. Firewall
```bash
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
```
Порт приложения (8000) наружу не открывается — только через Caddy
(reverse proxy на `127.0.0.1:8000`).

### 5. Доступ к приватному репозиторию (deploy key)
Под пользователем `deploy`:
```bash
ssh-keygen -t ed25519 -f ~/.ssh/github_carpool -N "" -C "carpool-vps-deploy"
cat ~/.ssh/github_carpool.pub
```
Публичный ключ добавить в
`https://github.com/glorden/carpool-queue/settings/keys` → **Add deploy
key**, без права записи (read-only).

Затем `~/.ssh/config` пользователя `deploy`:
```
Host github.com
  HostName github.com
  User git
  IdentityFile ~/.ssh/github_carpool
  IdentitiesOnly yes
```

### 6. Клонирование и настройка приложения
Под пользователем `deploy`:
```bash
git clone git@github.com:glorden/carpool-queue.git /home/deploy/carpool-queue
cd /home/deploy/carpool-queue
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

`.env` создаётся вручную на сервере (в `.gitignore`, из репозитория не
приходит) с новым, отдельным от локального, `SECRET_KEY`:
```bash
.venv/bin/python3 -c "import secrets; print(secrets.token_hex(32))"
```
```
DATABASE_URL=sqlite:///./carpool.db
SECRET_KEY=<сгенерированное значение>
```

Миграции (создают чистую прод-БД; локальная `carpool.db` с тестовыми
данными на сервер не переносится):
```bash
.venv/bin/alembic upgrade head
```

### 7. systemd-сервис
`/etc/systemd/system/carpool-queue.service`:
```ini
[Unit]
Description=Carpool Queue FastAPI service
After=network.target

[Service]
User=deploy
Group=deploy
WorkingDirectory=/home/deploy/carpool-queue
ExecStart=/home/deploy/carpool-queue/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```
```bash
systemctl daemon-reload
systemctl enable --now carpool-queue
```

### 8. Caddy — reverse proxy + автоматический HTTPS
`/etc/caddy/Caddyfile`:
```
zakaz.glorden.ru {
    reverse_proxy 127.0.0.1:8000
}
```
```bash
systemctl reload caddy
```
Caddy сам выпускает и продлевает сертификат Let's Encrypt.

## Добавление пользователей на проде

Отдельного API для этого нет — пользователи добавляются скриптом
(ставит человека в конец очереди):
```bash
cd /home/deploy/carpool-queue
.venv/bin/python -m scripts.add_user "Имя Фамилия" username
```

Для диспетчера/админа (создаёт заказы, но сам не в очереди):
```bash
.venv/bin/python -m scripts.add_user "Имя Фамилия" username --no-queue
```

## Обновление прод-сервера при новых коммитах

Под пользователем `deploy`:
```bash
cd /home/deploy/carpool-queue
git pull
.venv/bin/pip install -r requirements.txt
.venv/bin/alembic upgrade head
sudo systemctl restart carpool-queue
```
(`pip install` можно пропустить, если `requirements.txt` не менялся;
`alembic upgrade head` безопасно запускать всегда — если новых миграций
нет, ничего не произойдёт.)

## Где что лежит

| Что | Где |
|---|---|
| Код приложения | `/home/deploy/carpool-queue` |
| Виртуальное окружение | `/home/deploy/carpool-queue/.venv` |
| `.env` (секреты) | `/home/deploy/carpool-queue/.env` |
| БД (SQLite) | `/home/deploy/carpool-queue/carpool.db` |
| systemd unit | `/etc/systemd/system/carpool-queue.service` |
| Caddyfile | `/etc/caddy/Caddyfile` |
| SSH-ключ для GitHub (deploy key) | `/home/deploy/.ssh/github_carpool` |

## Troubleshooting

- Статус приложения: `systemctl status carpool-queue`
- Логи приложения: `journalctl -u carpool-queue -f`
- Статус Caddy: `systemctl status caddy`
- Логи Caddy: `journalctl -u caddy -f`
- Проверить синтаксис Caddyfile: `caddy validate --config /etc/caddy/Caddyfile`
- Проверить, что приложение отвечает локально (минуя Caddy):
  `curl http://127.0.0.1:8000/`
- Открытые порты: `ufw status verbose`

## Известные ограничения после деплоя

Технический долг с identity-проверками в `/orders/{id}/respond` и
`/orders/{id}/complete` (см. [ARCHITECTURE.md](./ARCHITECTURE.md))
осознанно не устранялся перед этим деплоем — решение принято оставить
как есть для текущего масштаба (доверенная группа из 10 человек).
