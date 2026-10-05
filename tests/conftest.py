from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
BASE = "https://books.toscrape.com/"
MYSTERY = BASE + "catalogue/category/books/mystery_3/index.html"
TRAVEL = BASE + "catalogue/category/books/travel_2/index.html"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class FakeFetcher:
    """Отдаёт сохранённые страницы вместо сети. Любая карточка товара — book.html."""

    def __init__(self, pages: dict[str, str], broken: set[str] | None = None):
        self.pages = pages
        self.broken = broken or set()
        self.calls: list[str] = []

    def get(self, url: str) -> str:
        from web_parser.fetcher import FetchError

        self.calls.append(url)
        if url in self.broken:
            raise FetchError(f"HTTP 503: {url}")
        if url in self.pages:
            return self.pages[url]
        if "/catalogue/" in url and "/category/" not in url:
            return fixture("book.html")
        raise FetchError(f"HTTP 404: {url}")


@pytest.fixture
def site_pages() -> dict[str, str]:
    return {
        BASE: fixture("index.html"),
        MYSTERY: fixture("category_mystery_p1.html"),
        MYSTERY.replace("index.html", "page-2.html"): fixture("category_mystery_p2.html"),
        TRAVEL: fixture("category_travel.html"),
    }
