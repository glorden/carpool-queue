# Прогресс проекта Carpool Queue

Здесь фиксируем, что уже сделано, чтобы не терять контекст между сессиями.

## ✅ Шаг 1: Каркас проекта
- Создана структура папок (`app/`, `deploy/`)
- Минимальное FastAPI-приложение (`app/main.py`), отвечает `{"status": "ok", ...}` на `/`
- `requirements.txt` с базовыми зависимостями (fastapi, uvicorn, sqlmodel, alembic, python-dotenv, passlib)
- `.gitignore`, `.env.example`, `README.md`
- Проверено локально: `uvicorn app.main:app --reload` → страница отвечает корректно
- Python 3.13.3 в venv (совпадает с версией на сервере)

## ✅ Шаг 2: Приватный репозиторий на GitHub
- Репозиторий создан: https://github.com/glorden/carpool-queue
- Локальный git инициализирован, сделан первый коммит
- Настроена авторизация через браузер (git credential manager)
- Код запушен в ветку `main`

## ✅ Шаг 3: Модели БД + первая Alembic-миграция
- Созданы модели: `User`, `QueuePosition`, `Order`, `OrderOffer` (`app/models/`)
- Подключение SQLModel + SQLite настроено (`app/database.py`, `app/config.py`)
- Alembic инициализирован, подключён к моделям через `env.py` (target_metadata = SQLModel.metadata)
- `alembic.ini` настроен на `sqlite:///./carpool.db`
- Сгенерирована и применена первая миграция (`create initial tables`)
- Проверено: все таблицы созданы в `carpool.db` — `user`, `order`, `queueposition`, `orderoffer`, `alembic_version`

## Ещё впереди (по плану)
- Шаг 4: Очередь (только чтение) — эндпоинт `/queue`
- Шаг 5: Создание заказа — `/orders POST`
- Шаг 6: Принятие/отказ — `/orders/{id}/respond`
- Шаг 7: Завершение заказа — `/orders/{id}/complete`
- Шаг 8: История заказов — `/orders GET`
- Шаг 9: Простой интерфейс (HTML-страницы)
- Шаг 10: Деплой (Caddyfile, systemd unit, сервер)

## Логика очереди (напоминание, чтобы не забыть при разработке)
- Заказ предлагается первому в очереди
- Принял → выполнил → ушёл в конец очереди
- Отказался → остаётся на своей позиции, заказ уходит следующему
- Таймаутов на ответ нет — ждём сколько угодно, коммуникация идёт в личном чате участников
