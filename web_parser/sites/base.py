"""Интерфейс адаптера сайта.

Чтобы парсить новый сайт, достаточно унаследовать SiteAdapter и описать четыре метода:
где категории, какие товары на странице списка, где следующая страница и что взять из карточки.
Загрузка, повторы, потоки и выгрузка уже готовы в ядре.
"""

from abc import ABC, abstractmethod

from web_parser.models import Product


class SiteAdapter(ABC):
    name: str = ""
    start_url: str = ""

    @abstractmethod
    def categories(self, html: str, base_url: str) -> dict[str, str]:
        """Категории каталога: {название: ссылка на первую страницу}."""

    @abstractmethod
    def product_links(self, html: str, base_url: str) -> list[str]:
        """Ссылки на карточки товаров со страницы списка."""

    @abstractmethod
    def next_page(self, html: str, base_url: str) -> str | None:
        """Ссылка на следующую страницу списка или None, если страница последняя."""

    @abstractmethod
    def product(self, html: str, url: str) -> Product:
        """Данные товара из его карточки."""
