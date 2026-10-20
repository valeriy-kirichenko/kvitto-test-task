from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models.tariff import Tariff
from app.schemas.tariff import TariffOut

router = APIRouter(
    prefix="/tariffs",
    tags=["Tariffs"],
)


@router.get(
    "",
    response_model=list[TariffOut],
    summary="Список тарифов",
    description="Возвращает список тарифов: `[{ id, title, price }]`. Цены — в копейках.",
    responses={
        200: {
            "description": "Список тарифов",
            "content": {
                "application/json": {
                    "example": [
                        {"id": 1, "title": "basic", "price": 990000},
                        {"id": 2, "title": "standard", "price": 1990000},
                        {"id": 3, "title": "premium", "price": 2990000},
                    ]
                }
            },
        }
    },
)
async def get_tariffs(db: AsyncSession = Depends(get_db)) -> list[Tariff]:
    """``GET /tariffs``: список всех тарифов с ценами в копейках."""
    result = await db.execute(select(Tariff).order_by(Tariff.id))
    return list(result.scalars().all())
