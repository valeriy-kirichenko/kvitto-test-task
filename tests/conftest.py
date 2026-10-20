"""Общие фикстуры pytest.

Тестовая БД должна существовать заранее. Этот файл не создаёт базы данных.
"""

from collections.abc import Iterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.testclient import TestClient

from app.core.db import create_test_session_factory, get_db
from app.main import app


@pytest.fixture(scope="session")
def test_client() -> Iterator[TestClient]:
    """Запускает приложение с подключением к отдельной тестовой БД."""
    test_engine, test_session_local = create_test_session_factory()

    async def override_get_db():
        async with test_session_local() as session:
            yield session

    app.state.test_session_local = test_session_local
    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as client:
            try:
                yield client
            finally:
                # Закрываем engine в event loop TestClient, пока portal активен.
                client.portal.call(test_engine.dispose)
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def client(test_client: TestClient) -> TestClient:
    """HTTP-клиент для отдельного теста."""
    return test_client


@pytest.fixture
def db(test_client: TestClient) -> Iterator[AsyncSession]:
    """Сессия тестовой БД для проверок из синхронных тестов."""
    session_local = app.state.test_session_local
    session = test_client.portal.call(session_local)
    try:
        yield session
    finally:
        test_client.portal.call(session.close)
