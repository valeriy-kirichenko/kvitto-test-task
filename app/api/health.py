from datetime import UTC, datetime

from fastapi import APIRouter, status

from app.core.config import settings
from app.schemas.health import HealthResponse

router = APIRouter(
    prefix='/health',
    tags=['Health check'],
)

@router.get(
    '',
    status_code=status.HTTP_200_OK,
    summary='Проверка здоровья приложения',
    description=(
        'Возвращает статус приложения и базовую информацию. '
        'Используется для мониторинга и балансировщика нагрузки'
    ),
    responses={
        200: {
            'description': 'Приложение работает нормально',
            'content': {
                'application/json': {
                    'example': {
                        'status': 'healthy',
                        'app_name': 'API платежей',
                        'version': '1.0.0',
                        'timestamp': '2026-07-24T10:30:00Z',
                    }
                }
            }
        }
    },
)
def health_check() -> HealthResponse:
    """Health check эндпоинт."""

    return HealthResponse(
        status='healthy',
        app_name=settings.APP_NAME,
        version=settings.APP_VERSION,
        timestamp=datetime.now(tz=UTC),
    )
