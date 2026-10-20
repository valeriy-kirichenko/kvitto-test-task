from datetime import datetime

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Схема ответа для health check эндпоинта"""

    status: str = Field(
        default='healthy',
        description='Статус приложения',
        examples=['healthy']
    )

    app_name: str = Field(
        description='Название приложения', examples=['API платежей']
    )

    version: str = Field(description='Версия API', examples=['1.0.0'])

    timestamp: datetime = Field(
        description='Время проверки', examples=['2026-10-20T10:30:00Z']
    )
