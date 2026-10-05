"""Адаптеры сайтов. Новый сайт: класс-наследник SiteAdapter + строка в ADAPTERS."""

from web_parser.sites.base import SiteAdapter
from web_parser.sites.books import BooksToScrape

ADAPTERS: dict[str, type[SiteAdapter]] = {
    BooksToScrape.name: BooksToScrape,
}
