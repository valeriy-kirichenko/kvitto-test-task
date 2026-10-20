from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.engine import make_url

from app.api import health
from app.core.config import settings
from app.core.db import check_connection


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Жизненный цикл приложения."""
    print(f"Запускаем {settings.APP_NAME} v{settings.APP_VERSION}")
    print(f"Debug mode: {settings.DEBUG}")

    # Проверка соединения с PostgreSQL: при недоступности БД старт
    # завершается ошибкой, а не «тихо» без соединения.
    await check_connection()
    print(f"База данных доступна: {make_url(settings.DATABASE_URL)}")

    yield

    print("Останавливаем приложение...")
    print("Приложение остановлено")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=settings.APP_DESCRIPTION,
    docs_url=settings.DOCS_URL,
    redoc_url=settings.REDOC_URL,
    openapi_url=settings.OPENAPI_URL,
    lifespan=lifespan,
)

app.include_router(health.router, prefix=settings.API_PREFIX)


@app.get(
    "/",
    tags=["Root"],
    summary="Корневой эндпоинт",
    description="Приветственный эндпоинт",
)
async def root():
    """Корневой эндпоинт."""
    return {
        "message": f"Добро пожаловать в {settings.APP_NAME}!",
        "docs": settings.DOCS_URL,
    }
