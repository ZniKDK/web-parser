"""Модель товара — общая для всех сайтов."""

from dataclasses import dataclass, fields


@dataclass
class Product:
    title: str
    url: str
    category: str = ""
    price: float | None = None
    currency: str = ""
    in_stock: bool = False
    stock_count: int | None = None
    rating: int | None = None
    sku: str = ""
    description: str = ""
    image_url: str = ""

    @classmethod
    def columns(cls) -> list[str]:
        return [f.name for f in fields(cls)]


# Русские заголовки столбцов для выгрузки
COLUMN_TITLES = {
    "title": "Название",
    "url": "Ссылка",
    "category": "Категория",
    "price": "Цена",
    "currency": "Валюта",
    "in_stock": "В наличии",
    "stock_count": "Остаток, шт.",
    "rating": "Рейтинг (1–5)",
    "sku": "Артикул (UPC)",
    "description": "Описание",
    "image_url": "Фото",
}
