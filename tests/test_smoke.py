import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, settings


async def test_app_starts(client: httpx.AsyncClient) -> None:
    """Фикстура client работает => приложение стартовало без краша."""
    assert client is not None


async def test_root_returns_json(client: httpx.AsyncClient) -> None:
    """Корневой эндпоинт: 200 и корректный JSON (без упоминания несуществующих настроек)."""
    response = await client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"message", "docs"}
    assert body["message"] == f"Добро пожаловать в {settings.APP_NAME}!"
    assert body["docs"] == settings.DOCS_URL


async def test_db_session_works(client: httpx.AsyncClient, db: AsyncSession) -> None:
    """Фикстура db: сессия приложения отвечает на ``SELECT 1``.

    Async-операция выполняется через ``await`` в event loop'е асинхронного
    теста (см. conftest), без TestClient и portal.call.
    """
    result = await db.execute(text("SELECT 1"))
    assert result.scalar_one() == 1


def test_settings_declares_fields() -> None:
    """S1: Settings объявляет DEBUG/DATABASE_URL/TEST_DATABASE_URL/WEBHOOK_SECRET."""
    for name in ("DEBUG", "DATABASE_URL", "TEST_DATABASE_URL", "WEBHOOK_SECRET"):
        assert name in Settings.model_fields, f"Settings.{name} не объявлен"
    assert Settings.model_fields["DEBUG"].default is False
    assert "asyncpg" in Settings.model_fields["DATABASE_URL"].default
