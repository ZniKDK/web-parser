"""Обход каталога: страницы списков по очереди, карточки товаров — параллельно."""

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from web_parser.fetcher import FetchError, Fetcher
from web_parser.models import Product
from web_parser.sites.base import SiteAdapter

log = logging.getLogger(__name__)


@dataclass
class ScrapeResult:
    products: list[Product] = field(default_factory=list)
    # Ошибки не прерывают обход: (ссылка, причина) попадают в отдельный лист отчёта
    errors: list[tuple[str, str]] = field(default_factory=list)


class Scraper:
    def __init__(self, fetcher: Fetcher, adapter: SiteAdapter, workers: int = 4):
        self.fetcher = fetcher
        self.adapter = adapter
        self.workers = workers

    def categories(self) -> dict[str, str]:
        html = self.fetcher.get(self.adapter.start_url)
        return self.adapter.categories(html, self.adapter.start_url)

    def collect_links(self, start_url: str, limit: int | None = None) -> list[str]:
        """Проходит пагинацию и собирает ссылки на карточки (без дублей, в порядке каталога)."""
        links: list[str] = []
        seen: set[str] = set()
        url: str | None = start_url
        visited_pages: set[str] = set()
        while url and url not in visited_pages:
            visited_pages.add(url)  # защита от зацикленной пагинации
            html = self.fetcher.get(url)
            for link in self.adapter.product_links(html, url):
                if link not in seen:
                    seen.add(link)
                    links.append(link)
            if limit and len(links) >= limit:
                return links[:limit]
            url = self.adapter.next_page(html, url)
        return links

    def scrape_products(
        self, links: list[str], on_progress: Callable[[], None] | None = None
    ) -> ScrapeResult:
        result = ScrapeResult()
        by_link: dict[str, Product] = {}
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            futures = {pool.submit(self._scrape_one, link): link for link in links}
            for future in as_completed(futures):
                link = futures[future]
                try:
                    by_link[link] = future.result()
                except FetchError as error:
                    result.errors.append((link, str(error)))
                except Exception as error:
                    # Вёрстка карточки отличается от ожидаемой — фиксируем и идём дальше
                    log.exception("Не разобрана карточка %s", link)
                    result.errors.append((link, f"Ошибка разбора: {type(error).__name__}: {error}"))
                if on_progress:
                    on_progress()
        # Порядок как в каталоге, а не как завершились потоки
        result.products = [by_link[link] for link in links if link in by_link]
        return result

    def _scrape_one(self, link: str) -> Product:
        return self.adapter.product(self.fetcher.get(link), link)

    def run(
        self,
        start_urls: list[str],
        limit: int | None = None,
        on_links: Callable[[int], None] | None = None,
        on_progress: Callable[[], None] | None = None,
    ) -> ScrapeResult:
        links: list[str] = []
        seen: set[str] = set()
        for start in start_urls:
            remaining = limit - len(links) if limit else None
            if remaining is not None and remaining <= 0:
                break
            for link in self.collect_links(start, remaining):
                if link not in seen:
                    seen.add(link)
                    links.append(link)
        if on_links:
            on_links(len(links))
        return self.scrape_products(links, on_progress)
