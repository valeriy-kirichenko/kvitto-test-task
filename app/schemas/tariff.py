from pydantic import BaseModel, ConfigDict, Field


class TariffOut(BaseModel):
    """Тариф из ответа ``GET /tariffs``. Цена хранится в копейках (целое число)."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(description="Идентификатор тарифа", examples=[1])
    title: str = Field(description="Название тарифа", examples=["basic"])
    price: int = Field(description="Цена в копейках", examples=[990000])
