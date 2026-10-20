from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки приложения."""

    APP_NAME: str = Field(
        default="API платежей",
        description="Название приложения",
    )
    APP_DESCRIPTION: str = Field(
        default=(
            "Небольшой сервис, через который онлайн-школа принимает "
            "оплату курса через Квитто"
        ),
        description="Описание приложения",
    )
    APP_VERSION: str = Field(default="1.0.0", description="Версия API")
    DEBUG: bool = Field(default=False, description="Режим отладки приложения")

    DOCS_URL: str = Field(default="/docs", description="URL Swagger")
    REDOC_URL: str = Field(default="/redoc", description="URL Redoc")
    OPENAPI_URL: str = Field(
        default="/openapi.json",
        description="URL OpenAPI schema",
    )

    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/kvitto_db",
        description="URL основной базы данных",
    )
    TEST_DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/kvitto_test_db",
        description="URL отдельной тестовой базы данных",
    )
    WEBHOOK_SECRET: str | None = Field(
        default=None,
        description="Секрет проверки подписи вебхука; None — проверка отключена",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
