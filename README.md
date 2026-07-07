# Carpool Queue

Внутренний сервис для организации очереди водителей на межгородние поездки.

## Статус

Шаг 1 из плана: базовый каркас проекта (FastAPI запускается, отвечает "ok").

## Запуск локально

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Открыть в браузере: http://127.0.0.1:8000

Должно вернуться: `{"status": "ok", "message": "Carpool queue service is running"}`
