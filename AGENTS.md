# API платежей — правила работы агента

FastAPI + SQLAlchemy (async) + PostgreSQL 16: сервис приёма оплаты курса (тарифы, платежи, вебхук банка).
Отвечать на русском языке.

## Общие правила

- Работать только в рамках поставленной задачи; без дополнительных улучшений и рефакторинга, если это явно не запрошено
- Не менять архитектуру проекта, публичный API, модели данных, границы сервисного слоя или структуру приложений без явного указания
- Если задача неоднозначна или требует архитектурного решения — остановиться и сообщить о проблеме
- Предпочитать небольшие локальные изменения существующему коду
- Проверять фактическое состояние кода, а не полагаться на старое описание в документах

## Ключевые инварианты (не нарушать)

- Все суммы — **целые копейки**, без `float` (арифметика в `app/domain.py`)
- Промокод `KVITTO10` (регистр не важен) — скидка 10% (`price * 10 // 100`); неизвестный код — стандартный `422`
- Рассрочка — только 3/6/12 месяцев; сумма частей графика ровно равна сумме платежа (лишние копейки — в первые); для `card`/`sbp` — `installment_months` и `schedule` равны `null`
- Статусы: только `pending → succeeded`, `pending → failed`, `succeeded → refunded`; всё остальное — `409`, статус не меняется
- `Idempotency-Key` необязателен: повторный запрос с тем же ключом возвращает **первый** платёж с `200`, дубль не создаётся; fingerprint тела не делать
- Alembic — единственный механизм управления схемой; `Base.metadata.create_all()` запрещён
- `app/domain.py` и `tests/test_domain.py` — стабильное ядро: не менять без найденной конкретной ошибки

## Перед изменениями

- Изучить непосредственно связанный код и существующие тесты
- Запустить релевантные тесты до изменения кода, если это возможно в текущем окружении

## Python / FastAPI

- Окружение: `uv run`, Python 3.11 (`.python-version`); не добавлять новые зависимости без разрешения
- Не переносить существующую логику между слоями без явного задания
- Lint: `uv run ruff check app tests` (line-length 100, настройки в `pyproject.toml`)

## Тесты

- Отдельная тестовая БД `kvitto_test_db` (не `kvitto_db`); pytest БД не создаёт
- Не изменять существующие тестовые данные; не удалять тесты ради прохождения набора
- Новые тесты должны проверять реальное поведение; не менять production-код, чтобы тесты проходили
- После изменений запускать релевантные тесты; перед завершением — полный `pytest`

## Git

- Не делать commit или push без явного указания; не изменять историю Git
- Перед завершением проверить `git diff` и `git diff --check`

## Область ответственности агента

Можно самостоятельно: pytest-тесты; docstring; type hints; исправление очевидных локальных ошибок.

Не решать самостоятельно: архитектуру приложения; структуру доменной модели; границы сервисов; публичный API; крупные рефакторинги; изменение архитектурных паттернов; оптимизацию ORM без конкретной задачи; массовую переработку файлов. Если требуется такое решение — остановиться и сообщить.

## Завершение задачи

1. Проверить изменённые файлы, `git diff`, `git diff --check`
2. Запустить необходимые тесты
3. Сообщить: что изменено, какие файлы, какие тесты, результат, нерешённые проблемы

Не утверждать, что задача выполнена, если проверки фактически не запускались.

## Стек и команды

- Стек: Python 3.11, FastAPI 0.148, SQLAlchemy 2.1 (async, asyncpg), Alembic 1.20, PostgreSQL 16, uv, Docker Compose, pytest + httpx, ruff
- `docker compose up -d` — поднимает PostgreSQL 16 (+ создаёт `kvitto_test_db` через `docker/postgres/init-db.sh`)
- `docker compose up --build` — запуск приложения (API :8000, Swagger `/docs`)
- `uv run pytest` — полный набор
- `uv run pytest tests/test_payments.py` — конкретный файл; `-k <name>` — по имени
- `uv run ruff check app tests` — lint
- `uv run alembic upgrade head` — миграции основной БД (`DATABASE_URL`)
- `ALEMBIC_DATABASE_URL="$TEST_DATABASE_URL" uv run alembic upgrade head` — миграции тестовой БД (однократно)

## Карта проекта

```
app/
├── main.py              # FastAPI-приложение, lifespan: check_connection + seed_tariffs
├── domain.py            # чистая бизнес-логика: промокод, график рассрочки, TRANSITIONS (без ORM)
├── api/
│   ├── tariffs.py       # GET /tariffs
│   ├── payments.py      # POST /payments, GET /payments, GET /payments/{id}, Idempotency-Key
│   ├── webhooks.py      # POST /webhooks/bank, смена статуса, проверка подписи
│   └── health.py        # health-чек
├── schemas/             # Pydantic v2: payment.py, tariff.py, webhook.py, health.py
├── models/              # SQLAlchemy: payment.py, tariff.py, base.py (схема только через Alembic)
└── core/
    ├── config.py        # Settings (pydantic-settings): DATABASE_URL, TEST_DATABASE_URL, WEBHOOK_SECRET
    ├── db.py            # async engine, SessionLocal, create_test_session_factory, check_connection
    └── seed.py          # идемпотентный seed тарифов (basic/standard/premium)
tests/
├── conftest.py          # test_client: ASGITransport + LifespanManager, override get_db, очистка данных
├── test_domain.py       # юнит-тесты domain.py (стабильные)
├── test_payments.py     # платёж: промокод, рассрочка, идемпотентность
├── test_list_payments.py# фильтры email/status списка платежей
├── test_webhooks.py     # переходы статусов, 404/409
├── test_webhook_signature.py  # HMAC-SHA256 подпись X-Signature
├── test_tariffs.py / test_schemas.py / test_seed.py / test_smoke.py
alembic/versions/        # начальные миграции (tariffs, payments)
scripts/fill_db.py       # заполнение основной БД тестовыми данными
docker/postgres/init-db.sh  # создание kvitto_test_db при первом старте
```
