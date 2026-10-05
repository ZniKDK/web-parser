"""Адаптер для books.toscrape.com — открытой песочницы для тренировки парсинга."""

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from web_parser.models import Product
from web_parser.sites.base import SiteAdapter

RATINGS = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}
CURRENCIES = {"£": "GBP", "$": "USD", "€": "EUR", "₽": "RUB"}


def parse_price(text: str) -> tuple[float | None, str]:
    """«£51.77» → (51.77, "GBP"). Понимает и «1 234,50 ₽», «1.234,50», «1,234.50»."""
    currency = next((code for sign, code in CURRENCIES.items() if sign in text), "")
    digits = re.sub(r"[^\d.,]", "", text).strip(".,")
    if not digits:
        return None, currency
    if "," in digits and "." in digits:
        # Десятичный разделитель — тот, что стоит последним
        if digits.rfind(",") > digits.rfind("."):
            digits = digits.replace(".", "").replace(",", ".")
        else:
            digits = digits.replace(",", "")
    elif "," in digits:
        # «12,50» — копейки, «1,234» — разделитель тысяч
        whole, _, frac = digits.rpartition(",")
        digits = f"{whole.replace(',', '')}.{frac}" if len(frac) <= 2 else digits.replace(",", "")
    return float(digits), currency


def parse_stock(text: str) -> tuple[bool, int | None]:
    """«In stock (22 available)» → (True, 22)."""
    in_stock = "in stock" in text.lower()
    match = re.search(r"(\d+)\s+available", text)
    return in_stock, int(match.group(1)) if match else None


class BooksToScrape(SiteAdapter):
    name = "books"
    start_url = "https://books.toscrape.com/"

    def categories(self, html: str, base_url: str) -> dict[str, str]:
        soup = BeautifulSoup(html, "html.parser")
        # Первая ссылка «Books» — весь каталог, вложенные — категории
        links = soup.select(".side_categories ul li ul li a")
        return {a.get_text(strip=True): urljoin(base_url, a["href"]) for a in links}

    def product_links(self, html: str, base_url: str) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")
        return [urljoin(base_url, a["href"]) for a in soup.select("article.product_pod h3 a")]

    def next_page(self, html: str, base_url: str) -> str | None:
        link = BeautifulSoup(html, "html.parser").select_one("ul.pager li.next a")
        return urljoin(base_url, link["href"]) if link else None

    def product(self, html: str, url: str) -> Product:
        soup = BeautifulSoup(html, "html.parser")
        main = soup.select_one(".product_main")
        price, currency = parse_price(main.select_one(".price_color").get_text())
        in_stock, count = parse_stock(main.select_one(".availability").get_text(" ", strip=True))
        rating_tag = main.select_one(".star-rating")
        rating = next((RATINGS[c] for c in rating_tag["class"] if c in RATINGS), None) if rating_tag else None
        # Описание идёт сразу за заголовком «Product Description»; у части книг его нет
        description_tag = soup.select_one("#product_description + p")
        table = {row.th.get_text(strip=True): row.td.get_text(strip=True) for row in soup.select("table tr")}
        crumbs = soup.select("ul.breadcrumb li a")
        image = soup.select_one("#product_gallery img")
        return Product(
            title=main.h1.get_text(strip=True),
            url=url,
            category=crumbs[2].get_text(strip=True) if len(crumbs) > 2 else "",
            price=price,
            currency=currency,
            in_stock=in_stock,
            stock_count=count,
            rating=rating,
            sku=table.get("UPC", ""),
            description=description_tag.get_text(strip=True) if description_tag else "",
            image_url=urljoin(url, image["src"]) if image else "",
        )
