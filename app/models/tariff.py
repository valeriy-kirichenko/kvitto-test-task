from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class Tariff(BaseModel):
    """Тариф онлайн-школы. Цена хранится в копейках (целое число)."""

    __tablename__ = "tariffs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(64), unique=True)
    price: Mapped[int] = mapped_column(Integer)
