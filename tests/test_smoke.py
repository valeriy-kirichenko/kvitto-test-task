from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.testclient import TestClient

from app.core.config import Settings, settings


def test_app_starts(client: TestClient) -> None:
    """Фикстура client работает => приложение стартовало без краша."""
    assert client is not None


def test_root_returns_json(client: TestClient) -> None:
    """Корневой эндпоинт: 200 и корректный JSON (без упоминания несуществующих настроек)."""
    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"message", "docs"}
    assert body["message"] == f"Добро пожаловать в {settings.APP_NAME}!"
    assert body["docs"] == settings.DOCS_URL


def test_db_session_works(client: TestClient, db: AsyncSession) -> None:
    """Фикстура db: сессия приложения отвечает на ``SELECT 1``.

    Async-операция выполняется в loop'е TestClient (``client.portal.call``),
    как и все остальные async-вызовы фикстур (см. conftest).
    """

    async def _select_one() -> int:
        result = await db.execute(text("SELECT 1"))
        return result.scalar_one()

    assert client.portal.call(_select_one) == 1


def test_settings_declares_fields() -> None:
    """S1: Settings объявляет DEBUG/DATABASE_URL/TEST_DATABASE_URL/WEBHOOK_SECRET."""
    for name in ("DEBUG", "DATABASE_URL", "TEST_DATABASE_URL", "WEBHOOK_SECRET"):
        assert name in Settings.model_fields, f"Settings.{name} не объявлен"
    assert Settings.model_fields["DEBUG"].default is False
    assert "asyncpg" in Settings.model_fields["DATABASE_URL"].default
