# Carpool Queue

Внутренний сервис для организации очереди водителей на межгородние поездки.

- ✅ Шаг 1: базовый каркас проекта (FastAPI запускается, отвечает "ok")
- ✅ Шаг 2: код в приватном репозитории на GitHub
- ✅ Шаг 3: модели БД (User, QueuePosition, Order, OrderOffer) + первая Alembic-миграция
- ✅ Шаг 4: эндпоинт GET /queue — список пользователей в порядке очереди
- ✅ Шаг 5: эндпоинт POST /orders — создание нового заказа
- ✅ Шаг 6: эндпоинт POST /orders/{id}/respond — принятие/отказ от заказа
- ✅ Шаг 7: эндпоинт POST /orders/{id}/complete — завершение заказа
- ✅ Шаг 8: эндпоинт GET /orders — история заказов с фильтрами
- ✅ Шаг 9: простой веб-интерфейс (дэшборд + история заказов) на HTML/vanilla JS
- 🔄 Шаг 10: деплой на сервер (в процессе)

Подробный лог прогресса и план дальнейших шагов — в файле [PROGRESS.md](./PROGRESS.md).
Архитектурные решения, технический долг и формат работы — в файле [ARCHITECTURE.md](./ARCHITECTURE.md).

## Запуск локально (Windows, cmd.exe)

```cmd
cd C:\Users\Oleg\Desktop\carpool-queue
chcp 65001
.venv\Scripts\activate.bat
uvicorn app.main:app --reload
```

Открыть в браузере: http://127.0.0.1:8000

Должно вернуться: `{"status": "ok", "message": "Carpool queue service is running"}`

Веб-интерфейс (дэшборд и история заказов) доступен по адресу: http://127.0.0.1:8000/static/index.html
*(уточнить фактический путь при чтении PROGRESS.md/ARCHITECTURE.md — на месте поправим, если отличается)*

<details>
<summary>Первоначальная настройка (один раз) и запуск на Linux/macOS</summary>

Первоначальная настройка окружения:

```cmd
cd C:\Users\Oleg\Desktop\carpool-queue
python -m venv .venv
.venv\Scripts\activate.bat
pip install -r requirements.txt
```

Запуск на Linux/macOS:

```bash
source .venv/bin/activate
uvicorn app.main:app --reload
```

</details>

## База данных

Используется SQLite + SQLModel, миграции — через Alembic.

Перед первым запуском:

```bash
copy .env.example .env
alembic upgrade head
```

Это создаст файл `carpool.db` со всеми нужными таблицами.

Если менял модели и нужно создать новую миграцию:

```bash
alembic revision --autogenerate -m "описание изменения"
alembic upgrade head
```

## Эндпоинты

- `GET /` — проверка работоспособности сервиса
- `GET /queue` — список пользователей в текущем порядке очереди
- `POST /orders` — создать новый заказ (route, comment — опциональны)
- `POST /orders/{order_id}/respond` — принять/отклонить предложенный заказ
- `POST /orders/{order_id}/complete` — отметить заказ как завершённый (заказ должен быть в статусе `assigned`)
- `GET /orders` — история заказов; опциональные query-параметры `status`, `user_id`, `limit` (по умолчанию 100, максимум 500); сортировка по `created_at` (новые сверху)
- `GET /orders/pending` — заказы в статусе `pending` вместе с данными активного предложения (`OrderOffer`): кому именно сейчас предложен заказ и когда

Ошибки (несуществующий заказ, некорректный статус и т.п.) возвращаются в стандартном формате FastAPI: `{"detail": "..."}` с соответствующим HTTP-статусом (404/400).

## Веб-интерфейс

Простой дэшборд и история заказов на HTML/vanilla JS. Обслуживается FastAPI как статика.
Интерфейс полностью на русском языке (без переключателя языков).

## Технический долг

`/orders/{id}/respond` и `/orders/{id}/complete` пока не проверяют identity вызывающего (любой user_id может принять/отклонить/завершить любой заказ). Осознанное решение для доверенной группы из 10 человек. Детали и план устранения — в ARCHITECTURE.md.

## Тестовые данные

Для проверки очереди можно наполнить БД тестовыми пользователями:

```bash
python -m scripts.seed
```