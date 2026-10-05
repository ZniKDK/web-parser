"""Командная строка: python -m web_parser --help"""

import argparse
import logging
import sys
import time
from pathlib import Path

from tqdm import tqdm

from web_parser import export
from web_parser.fetcher import FetchError, Fetcher
from web_parser.scraper import Scraper
from web_parser.sites import ADAPTERS

PRODUCTS = ("товар", "товара", "товаров")

EXAMPLES = """
примеры:
  python -m web_parser --list-categories
  python -m web_parser --category Travel --out travel.xlsx
  python -m web_parser --category Travel --category Poetry --out books.csv
  python -m web_parser --limit 100 --out sample.xlsx
  python -m web_parser --out books.xlsx --sheet-id <ID таблицы> --credentials service_account.json
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="web_parser",
        description="Выгрузка каталога сайта в Excel, CSV или Google Таблицу.",
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--site", choices=sorted(ADAPTERS), default="books", help="адаптер сайта (по умолчанию books)")
    parser.add_argument("--list-categories", action="store_true", help="показать категории и выйти")
    parser.add_argument("-c", "--category", action="append", default=[],
                        help="категория (можно указать несколько раз); без неё — весь каталог")
    parser.add_argument("-n", "--limit", type=int, help="не больше N товаров (для пробного запуска)")
    parser.add_argument("-o", "--out", default="products.xlsx", help="файл результата: .xlsx или .csv")
    parser.add_argument("-w", "--workers", type=int, default=4, help="параллельных потоков (по умолчанию 4)")
    parser.add_argument("--delay", type=float, default=0.2, help="пауза между запросами, с (по умолчанию 0.2)")
    parser.add_argument("--retries", type=int, default=3, help="повторов при ошибке (по умолчанию 3)")
    parser.add_argument("--cache", default=".cache", help="папка кэша страниц (по умолчанию .cache)")
    parser.add_argument("--no-cache", action="store_true", help="не использовать кэш")
    parser.add_argument("--ignore-robots", action="store_true", help="не проверять robots.txt")
    parser.add_argument("--sheet-id", help="ID Google Таблицы для дополнительной выгрузки")
    parser.add_argument("--credentials", default="service_account.json", help="ключ сервисного аккаунта Google")
    parser.add_argument("-v", "--verbose", action="store_true", help="подробный журнал")
    return parser


def plural(n: int, forms: tuple[str, str, str]) -> str:
    """Склонение по числу: 1 товар, 2 товара, 5 товаров, 11 товаров, 21 товар."""
    if n % 10 == 1 and n % 100 != 11:
        form = forms[0]
    elif 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        form = forms[1]
    else:
        form = forms[2]
    return f"{n} {form}"


def resolve_categories(wanted: list[str], available: dict[str, str]) -> list[str]:
    """Находит категории без учёта регистра. Неизвестная категория — понятная ошибка со списком."""
    lookup = {name.lower(): url for name, url in available.items()}
    urls = []
    for name in wanted:
        url = lookup.get(name.strip().lower())
        if not url:
            raise SystemExit(f"Нет категории «{name}». Список: python -m web_parser --list-categories")
        urls.append(url)
    return urls


def main(argv: list[str] | None = None) -> int:
    # Консоль Windows бывает в cp1251: неизвестный символ не должен ронять программу
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.ERROR,
                        format="%(asctime)s %(levelname)s %(message)s")
    out = Path(args.out)
    if out.suffix.lower() not in (".xlsx", ".csv"):
        print("Файл результата должен быть .xlsx или .csv", file=sys.stderr)
        return 2

    adapter = ADAPTERS[args.site]()
    fetcher = Fetcher(delay=args.delay, retries=args.retries, cache_dir=None if args.no_cache else args.cache,
                      respect_robots=not args.ignore_robots)
    scraper = Scraper(fetcher, adapter, workers=args.workers)
    started = time.monotonic()

    try:
        categories = scraper.categories()
        if args.list_categories:
            for name in categories:
                print(name)
            return 0
        starts = resolve_categories(args.category, categories) if args.category else [adapter.start_url]

        bar = tqdm(desc="Товары", unit="шт", disable=None)
        result = scraper.run(starts, limit=args.limit, on_links=lambda n: setattr(bar, "total", n),
                             on_progress=bar.update)
        bar.close()
    except FetchError as error:
        print(f"Ошибка загрузки: {error}", file=sys.stderr)
        return 1

    if out.suffix.lower() == ".csv":
        export.to_csv(result.products, out)
    else:
        export.to_xlsx(result.products, out, errors=result.errors, source=adapter.start_url)

    seconds = time.monotonic() - started
    print(f"Готово: {plural(len(result.products), PRODUCTS)} -> {out} за {seconds:.0f} с "
          f"(запросов: {fetcher.stats['requests']}, из кэша: {fetcher.stats['cache_hits']}).")
    if result.errors:
        print(f"Пропущено с ошибками: {len(result.errors)} (подробности на листе «Ошибки» или в журнале -v).")

    if args.sheet_id:
        url = export.to_google_sheet(result.products, args.sheet_id, args.credentials)
        print(f"Google Таблица обновлена: {url}")
    return 0
