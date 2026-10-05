import pytest

from tests.conftest import BASE, MYSTERY, TRAVEL, fixture
from web_parser.sites.books import BooksToScrape, parse_price, parse_stock

adapter = BooksToScrape()


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("£51.77", (51.77, "GBP")),
        ("1 234,50 ₽", (1234.50, "RUB")),
        ("1.234,50 €", (1234.50, "EUR")),
        ("$1,234.50", (1234.50, "USD")),
        ("1,234 ₽", (1234.0, "RUB")),
        ("12,5", (12.5, "")),
        ("по запросу", (None, "")),
    ],
)
def test_parse_price(text, expected):
    assert parse_price(text) == expected


def test_parse_stock():
    assert parse_stock("In stock (22 available)") == (True, 22)
    assert parse_stock("In stock") == (True, None)
    assert parse_stock("Out of stock") == (False, None)


def test_categories():
    categories = adapter.categories(fixture("index.html"), BASE)
    assert len(categories) == 50
    assert categories["Travel"] == TRAVEL
    assert "Books" not in categories  # корневая ссылка — это весь каталог, не категория


def test_product_links_and_pagination():
    html = fixture("category_mystery_p1.html")
    links = adapter.product_links(html, MYSTERY)
    assert len(links) == 20
    assert all(link.startswith(BASE + "catalogue/") and link.endswith("/index.html") for link in links)
    assert "/category/" not in links[0]
    assert adapter.next_page(html, MYSTERY) == MYSTERY.replace("index.html", "page-2.html")


def test_last_page_has_no_next():
    assert adapter.next_page(fixture("category_travel.html"), TRAVEL) is None


def test_product_card():
    url = BASE + "catalogue/a-light-in-the-attic_1000/index.html"
    product = adapter.product(fixture("book.html"), url)
    assert product.title == "A Light in the Attic"
    assert product.price == 51.77
    assert product.currency == "GBP"
    assert product.in_stock is True
    assert product.stock_count == 22
    assert product.rating == 3
    assert product.category == "Poetry"
    assert product.sku == "a897fe39b1053632"
    assert product.description.startswith("It's hard to imagine")
    assert product.image_url.startswith(BASE + "media/cache/")


def test_product_without_description():
    html = fixture("book.html").replace('id="product_description"', 'id="other"')
    product = adapter.product(html, BASE + "catalogue/x/index.html")
    assert product.description == ""
    assert product.title == "A Light in the Attic"
