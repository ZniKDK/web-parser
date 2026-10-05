from tests.conftest import BASE, MYSTERY, TRAVEL, FakeFetcher
from web_parser.scraper import Scraper
from web_parser.sites.books import BooksToScrape


def make(pages, broken=None, workers=4):
    fetcher = FakeFetcher(pages, broken)
    return Scraper(fetcher, BooksToScrape(), workers=workers), fetcher


def test_collect_links_follows_pagination(site_pages):
    scraper, _ = make(site_pages)
    links = scraper.collect_links(MYSTERY)
    assert len(links) == 32  # 20 на первой странице + 12 на второй
    assert len(set(links)) == 32


def test_collect_links_stops_at_limit(site_pages):
    scraper, fetcher = make(site_pages)
    links = scraper.collect_links(MYSTERY, limit=5)
    assert len(links) == 5
    assert fetcher.calls == [MYSTERY]  # вторая страница не нужна — лишних запросов нет


def test_pagination_loop_protection(site_pages):
    # Страница ссылается сама на себя как на «следующую» — обход не должен зациклиться
    looped = site_pages[TRAVEL].replace('<ul class="pager">', '<ul class="pager"><li class="next"><a href="index.html">next</a></li>')
    pages = {**site_pages, TRAVEL: looped}
    scraper, _ = make(pages)
    assert len(scraper.collect_links(TRAVEL)) == 11


def test_run_keeps_catalog_order(site_pages):
    scraper, _ = make(site_pages, workers=8)
    links = scraper.collect_links(TRAVEL)
    result = scraper.run([TRAVEL])
    assert [p.url for p in result.products] == links
    assert result.errors == []


def test_run_several_categories_with_limit(site_pages):
    scraper, _ = make(site_pages)
    result = scraper.run([TRAVEL, MYSTERY], limit=15)
    # 11 книг Travel целиком, остаток лимита — из Mystery
    assert len(result.products) == 15
    assert len({p.url for p in result.products}) == 15


def test_errors_do_not_stop_scraping(site_pages):
    scraper, _ = make(site_pages)
    links = scraper.collect_links(TRAVEL)
    scraper, _ = make(site_pages, broken={links[0], links[3]})
    progress = []
    result = scraper.run([TRAVEL], on_progress=lambda: progress.append(1))
    assert len(result.products) == 9
    assert {link for link, _ in result.errors} == {links[0], links[3]}
    assert len(progress) == 11  # прогресс учитывает и неудачные карточки


def test_broken_layout_reported_as_error(site_pages):
    scraper, _ = make(site_pages)
    links = scraper.collect_links(TRAVEL)
    pages = {**site_pages, links[1]: "<html><body>Страница изменилась</body></html>"}
    scraper, _ = make(pages)
    result = scraper.run([TRAVEL])
    assert len(result.products) == 10
    assert "Ошибка разбора" in result.errors[0][1]


def test_categories_from_start_page(site_pages):
    scraper, fetcher = make(site_pages)
    assert "Mystery" in scraper.categories()
    assert fetcher.calls == [BASE]
