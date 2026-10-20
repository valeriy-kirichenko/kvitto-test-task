"""Общие фикстуры pytest.

Тестовая БД должна существовать заранее. Этот файл не создаёт базы данных.
"""

from collections.abc import AsyncIterator

import httpx
import pytest_asyncio
from asgi_lifespan import LifespanManager
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import create_test_session_factory, get_db
from app.main import app


@pytest_asyncio.fixture(scope="session")
async def test_client() -> AsyncIterator[httpx.AsyncClient]:
    """Запускает приложение с подключением к отдельной тестовой БД.

    Запросы идут через ``httpx.ASGITransport`` (ASGI-приложение без реального
    HTTP-сервера), а lifecycle приложения (``check_connection`` + ``seed_tariffs``)
    запускается и останавливается явно через ``LifespanManager`` — ``ASGITransport``
    сам lifespan не поднимает, в отличие от ``TestClient``.

    Фикстура сессий (engine + фабрика сессий) создаётся и закрывается в одном
    event loop'е, поэтому ресурсы SQLAlchemy не пересекаются между loop'ами.
    """
    test_engine, test_session_local = create_test_session_factory()

    async def override_get_db():
        async with test_session_local() as session:
            yield session

    app.state.test_session_local = test_session_local
    app.dependency_overrides[get_db] = override_get_db

    try:
        async with LifespanManager(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                try:
                    yield client
                finally:
                    # Закрываем тестовый engine в том же event loop'е, в котором
                    # он создавался и использовался (аналог прежнего portal.call).
                    await test_engine.dispose()
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture
async def client(test_client: httpx.AsyncClient) -> httpx.AsyncClient:
    """HTTP-клиент для отдельного теста."""
    return test_client


@pytest_asyncio.fixture
async def db(test_client: httpx.AsyncClient) -> AsyncIterator[AsyncSession]:
    """Сессия тестовой БД для проверок из асинхронных тестов."""
    session_local = app.state.test_session_local
    session = session_local()
    try:
        yield session
    finally:
        await session.close()
