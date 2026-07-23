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
apt-get install -y python3-venv python3-pip git ufw curl sqlite3
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

## Бэкап базы данных

Ежедневный `sqlite3 .backup` через cron под пользователем `deploy`,
скрипт — `scripts/backup_db.sh` (см. ARCHITECTURE.md — там же логика
хранения). Копии лежат в `backups/` рядом с `carpool.db`, в Git не
попадают (`*.db` в `.gitignore`).

Настройка (один раз, под пользователем `deploy`):
```bash
chmod +x /home/deploy/carpool-queue/scripts/backup_db.sh
crontab -e
```
Добавить строку:
```
15 3 * * * /home/deploy/carpool-queue/scripts/backup_db.sh >> /home/deploy/carpool-queue/backups/backup.log 2>&1
```

Восстановление из копии (сервис нужно остановить на время):
```bash
sudo systemctl stop carpool-queue
cp backups/carpool-2026-07-22.db carpool.db
sudo systemctl start carpool-queue
```

## Добавление пользователей на проде

Отдельного API для этого нет — пользователи добавляются скриптом
(по умолчанию ставит человека в конец обеих очередей — дальней и
короткой):
```bash
cd /home/deploy/carpool-queue
.venv/bin/python -m scripts.add_user "Имя Фамилия" username
```

Только в одну из очередей:
```bash
.venv/bin/python -m scripts.add_user "Имя Фамилия" username --queue-type=long
.venv/bin/python -m scripts.add_user "Имя Фамилия" username --queue-type=short
```

Для диспетчера/админа (создаёт заказы, но сам не в очереди):
```bash
.venv/bin/python -m scripts.add_user "Имя Фамилия" username --no-queue
```

## Перестановка порядка в очереди на проде

Для редкой ручной правки. Первый аргумент — тип очереди (`long` или
`short`), дальше — ровно те же username, что сейчас в этой очереди,
в нужном порядке; вторая очередь не затрагивается:
```bash
cd /home/deploy/carpool-queue
.venv/bin/python -m scripts.reorder_queue long username1 username2 username3
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
`alembic upgrade head` обычно безопасно запускать всегда — если новых
миграций нет, ничего не произойдёт.)

**Исключение — миграции, которые на SQLite требуют `batch_alter_table`
(пересоздание таблицы: смена `NOT NULL`, constraint'ов и т.п., а не
только `add_column`).** SQLite не даёт транзакционный DDL, поэтому
запись от ещё не перезапущенного старого процесса в это окно может
провалиться. Для таких миграций — сначала остановить сервис, сделать
ручной снэпшот, потом мигрировать:
```bash
sudo systemctl stop carpool-queue
sqlite3 carpool.db ".backup carpool-pre-<название миграции>.db"
.venv/bin/alembic upgrade head
sudo systemctl start carpool-queue
```
Первый пример такой миграции — `5437dcec06ba` (Шаг 23, вторая очередь).

## Где что лежит

| Что | Где |
|---|---|
| Код приложения | `/home/deploy/carpool-queue` |
| Виртуальное окружение | `/home/deploy/carpool-queue/.venv` |
| `.env` (секреты) | `/home/deploy/carpool-queue/.env` |
| БД (SQLite) | `/home/deploy/carpool-queue/carpool.db` |
| Бэкапы БД | `/home/deploy/carpool-queue/backups/` |
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
