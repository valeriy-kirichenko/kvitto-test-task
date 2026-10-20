# Квитто — API платежей

Небольшой сервис для приёма оплаты курса через Квитто: тарифы, платежи (карта / СБП / рассрочка), идемпотентная повторная отправка и вебхук смен статуса от банка.

- Все суммы — целое число копеек, без `float`.
- Промокод `KVITTO10` (регистр не важен) даёт скидку 10%, неизвестный код — `422`.
- Рассрочка — 3, 6 или 12 месяцев; сумма частей графика ровно равна сумме платежа, лишние копейки — в первые платежи.
- `Idempotency-Key` необязателен: повторный запрос с тем же ключом возвращает первый платёж с кодом `200`, дубль не создаётся.
- Статусы: `pending → succeeded`, `pending → failed`, `succeeded → refunded`; остальные переходы — `409`, статус не меняется.

## Стек

- Python 3.11+, FastAPI, Pydantic v2
- PostgreSQL 16, SQLAlchemy 2.1 (async, asyncpg)
- Alembic (единственный механизм управления схемой), миграции
- pytest + httpx, ruff
- uv, Docker / Docker Compose

## Требования

- Python 3.11+ (в Docker-образе — `python:3.11-slim`)
- uv
- Docker + Docker Compose (PostgreSQL 16 поднимается контейнером)

## Настройка окружения

Скопируйте пример и подставьте значения под своё окружение:

```bash
cp .env.example .env
```

Варианты из `.env.example`:

| Переменная | Где используется |
|---|---|
| `DATABASE_URL` | API, локальный запуск с хост-машины |
| `TEST_DATABASE_URL` | тестовая БД (локальный запуск тестов) |
| `COMPOSE_DATABASE_URL` | API внутри Docker Compose (указывает на `postgres:5432`) |
| `COMPOSE_TEST_DATABASE_URL` | тестовая БД для контейнера API |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | контейнер PostgreSQL |
| `WEBHOOK_SECRET` | проверка подписи вебхука: `X-Signature` = hex HMAC-SHA256 от исходного тела запроса; пустое/отсутствующее значение — проверка выключена; при настроенном секрете неверная/отсутствующая подпись — `401` |

`.env` не попадает в git (см. `.gitignore`).

## Запуск через Docker Compose

```bash
docker compose up --build
```

- API: http://localhost:8000
- Swagger: http://localhost:8000/docs
- PostgreSQL: `localhost:5432` (volume `postgres_data`, данные переживают перезапуск)

При старте контейнер сначала применяет миграции Alembic к основной БД (`alembic upgrade head`, идемпотентно — на «новой» машине отдельный шаг миграций при этом не нужен), затем после `service_healthy` у PostgreSQL API проверяет соединение (`SELECT 1`) и идемпотентно добавляет три тарифа (`basic` — 990 000, `standard` — 1 990 000, `premium` — 2 990 000 копеек). Код приложения и миграции монтируются в контейнер, изменения `app/` и `alembic/` подхватываются без пересборки изображения.

## Миграции

Alembic — единственный механизм управления схемой (без `create_all`).

При запуске через Docker Compose миграции в основную БД применяются автоматически
внутри контейнера API при старте (см. раздел выше) — вручную выполнять их в этом
случае не нужно.

Для локального запуска с хост-машины и для тестовой БД применяйте вручную:

```bash
# основная БД (URL из DATABASE_URL):
uv run alembic upgrade head

# тестовая БД (URL из TEST_DATABASE_URL):
ALEMBIC_DATABASE_URL="$TEST_DATABASE_URL" uv run alembic upgrade head
```

## Тесты

Тесты работают с отдельной БД `kvitto_test_db`, отличной от основной `kvitto_db`; на первом запуске Postgres-контейнера она создаётся скриптом `docker/postgres/init-db.sh`.

```bash
# 1) поднять инфраструктуру (однократно):
docker compose up -d

# 2) применить миграции к тестовой БД (однократно):
ALEMBIC_DATABASE_URL="$TEST_DATABASE_URL" uv run alembic upgrade head

# 3) запускать:
uv run pytest          # полный набор
uv run pytest tests/test_payments.py -k idempotency   # конкретный тест
uv run ruff check app tests
```

Тесты не создают базу данных и не изменяют основную БД; данные очищаются между тестами.

## CI

GitHub Actions (`.github/workflows/ci.yml`) на каждый push/PR запускает `ruff check app tests` и `pytest` против PostgreSQL 16: создаёт `kvitto_test_db`, применяет миграции и прогоняет полный набор тестов.

## Эндпоинты и примеры

### `GET /tariffs` — список тарифов

```bash
curl http://localhost:8000/tariffs
```

### `POST /payments` — создать платёж

```bash
# карта + промокод (регистр не важен), новый платёж — 201:
curl -X POST http://localhost:8000/payments \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: order-123" \
  -d '{
    "tariff_id": 2,
    "email": "user@example.com",
    "method": "card",
    "promo_code": "kvitto10"
  }'

# та же Idempotency-Key повторно — 200, возвращается первый платёж:
curl -i -X POST http://localhost:8000/payments \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: order-123" \
  -d '{"tariff_id": 2, "email": "user@example.com", "method": "card"}'

# рассрочка на 3 месяца (standard 1 990 000 коп.):
# schedule = [663 334, 663 333, 663 333]
curl -X POST http://localhost:8000/payments \
  -H "Content-Type: application/json" \
  -d '{
    "tariff_id": 2,
    "email": "user@example.com",
    "method": "installment",
    "installment_months": 3
  }'
```

### `GET /payments` — список платежей (опциональные фильтры `email`, `status`)

```bash
# все платежи:
curl http://localhost:8000/payments

# фильтры:
curl "http://localhost:8000/payments?email=user@example.com"
curl "http://localhost:8000/payments?status=pending"
curl "http://localhost:8000/payments?email=user@example.com&status=succeeded"
```

### `GET /payments/{id}` — платёж по id (404, если его нет)

```bash
curl http://localhost:8000/payments/1
```

### `POST /webhooks/bank` — смена статуса от банка

```bash
# разрешённый переход pending → succeeded — 200:
curl -X POST http://localhost:8000/webhooks/bank \
  -H "Content-Type: application/json" \
  -d '{"payment_id": 1, "status": "succeeded"}'

# запрещённый переход (например, refunded → pending) — 409:
curl -i -X POST http://localhost:8000/webhooks/bank \
  -H "Content-Type: application/json" \
  -d '{"payment_id": 1, "status": "pending"}'
```

#### Подпись вебхука (бонус)

Если в окружении настроен непустой `WEBHOOK_SECRET`, запрос обязан содержать
заголовок `X-Signature` — hex HMAC-SHA256 от **исходного** тела запроса.
Неверная или отсутствующая подпись — `401`. При пустом/отсутствующем
`WEBHOOK_SECRET` проверка выключена (dev-режим).

```bash
# вычислить подпись и отправить подписанный запрос:
BODY='{"payment_id": 1, "status": "succeeded"}'
SIGNATURE=$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac "$WEBHOOK_SECRET" | awk '{print $2}')

curl -X POST http://localhost:8000/webhooks/bank \
  -H "Content-Type: application/json" \
  -H "X-Signature: ${SIGNATURE}" \
  -d "${BODY}"
```

Ошибки валидации — стандартные `422` от FastAPI.
