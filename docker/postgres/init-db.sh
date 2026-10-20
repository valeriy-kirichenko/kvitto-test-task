#!/usr/bin/env bash
# Инициализация контейнера PostgreSQL при ПЕРВОМ запуске (пустая data-директория).
#
# Создаёт отдельную тестовую базу данных kvitto_test_db, если её ещё нет.
# Основная БД (kvitto_db) создаётся автоматически entrypoint'ом из POSTGRES_DB.

set -euo pipefail

TEST_DB='kvitto_test_db'

count="$(psql -v ON_ERROR_STOP=1 --username "${POSTGRES_USER}" --dbname postgres \
  -tA -c "SELECT count(*) FROM pg_database WHERE datname = '${TEST_DB}'")"

if [ "${count}" -eq 0 ]; then
  psql -v ON_ERROR_STOP=1 --username "${POSTGRES_USER}" --dbname postgres \
    -c "CREATE DATABASE ${TEST_DB}"
fi
