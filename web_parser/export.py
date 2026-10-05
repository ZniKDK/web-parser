"""Выгрузка результата: CSV, оформленный Excel и (по желанию) Google Таблица."""

import csv
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from web_parser.models import COLUMN_TITLES, Product

HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
HEADER_FONT = Font(bold=True, color="FFFFFF")
LINK_FONT = Font(color="0563C1", underline="single")
# Ширина столбцов в символах: описание узкое, полный текст виден в ячейке при выделении
WIDTHS = {"title": 45, "url": 14, "category": 18, "price": 10, "currency": 8, "in_stock": 11,
          "stock_count": 12, "rating": 13, "sku": 19, "description": 60, "image_url": 10}


def _row(product: Product) -> dict:
    data = asdict(product)
    data["in_stock"] = "да" if product.in_stock else "нет"
    return data


def to_csv(products: list[Product], path: str | Path) -> Path:
    """CSV в UTF-8 с BOM и разделителем «;» — Excel открывает его двойным щелчком без «кракозябр»."""
    path = Path(path)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file, delimiter=";")
        writer.writerow([COLUMN_TITLES[c] for c in Product.columns()])
        for product in products:
            row = _row(product)
            writer.writerow(["" if row[c] is None else row[c] for c in Product.columns()])
    return path


def category_summary(products: list[Product]) -> list[dict]:
    groups: dict[str, list[Product]] = defaultdict(list)
    for product in products:
        groups[product.category or "Без категории"].append(product)
    summary = []
    for name, items in sorted(groups.items(), key=lambda pair: -len(pair[1])):
        prices = [p.price for p in items if p.price is not None]
        summary.append({
            "category": name,
            "count": len(items),
            "in_stock": sum(p.in_stock for p in items),
            "min": min(prices) if prices else None,
            "avg": round(sum(prices) / len(prices), 2) if prices else None,
            "max": max(prices) if prices else None,
        })
    return summary


def _style_header(sheet, columns: int) -> None:
    for col in range(1, columns + 1):
        cell = sheet.cell(row=1, column=col)
        cell.fill, cell.font = HEADER_FILL, HEADER_FONT
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    sheet.row_dimensions[1].height = 30
    sheet.freeze_panes = "A2"


def to_xlsx(products: list[Product], path: str | Path, errors: list[tuple[str, str]] | None = None,
            source: str = "") -> Path:
    path = Path(path)
    wb = Workbook()

    # Лист 1 — все товары
    sheet = wb.active
    sheet.title = "Товары"
    columns = Product.columns()
    sheet.append([COLUMN_TITLES[c] for c in columns])
    for product in products:
        row = _row(product)
        sheet.append([row[c] for c in columns])
    _style_header(sheet, len(columns))
    for index, name in enumerate(columns, 1):
        sheet.column_dimensions[get_column_letter(index)].width = WIDTHS.get(name, 14)
    price_col = columns.index("price") + 1
    for r in range(2, len(products) + 2):
        sheet.cell(row=r, column=price_col).number_format = "#,##0.00"
        # Длинные ссылки заменяем коротким кликабельным текстом
        for name, label in (("url", "открыть"), ("image_url", "фото")):
            cell = sheet.cell(row=r, column=columns.index(name) + 1)
            if cell.value:
                cell.hyperlink, cell.value, cell.font = cell.value, label, LINK_FONT
    if products:
        sheet.auto_filter.ref = f"A1:{get_column_letter(len(columns))}{len(products) + 1}"

    # Лист 2 — сводка по категориям
    summary = wb.create_sheet("Сводка")
    headers = ["Категория", "Товаров", "В наличии", "Мин. цена", "Средняя цена", "Макс. цена"]
    summary.append(headers)
    for item in category_summary(products):
        summary.append([item["category"], item["count"], item["in_stock"], item["min"], item["avg"], item["max"]])
    _style_header(summary, len(headers))
    for index, width in enumerate((28, 10, 11, 12, 14, 12), 1):
        summary.column_dimensions[get_column_letter(index)].width = width
    for row in summary.iter_rows(min_row=2, min_col=4, max_col=6):
        for cell in row:
            cell.number_format = "#,##0.00"
    last = summary.max_row + 2
    summary.cell(row=last, column=1, value="Всего товаров").font = Font(bold=True)
    summary.cell(row=last, column=2, value=len(products)).font = Font(bold=True)
    summary.cell(row=last + 1, column=1, value="Источник")
    summary.cell(row=last + 1, column=2, value=source)
    summary.cell(row=last + 2, column=1, value="Дата выгрузки")
    summary.cell(row=last + 2, column=2, value=datetime.now().strftime("%d.%m.%Y %H:%M"))

    # Лист 3 — ошибки, если были: заказчик видит, что пропущено и почему
    if errors:
        err = wb.create_sheet("Ошибки")
        err.append(["Ссылка", "Причина"])
        for link, reason in errors:
            err.append([link, reason])
        _style_header(err, 2)
        err.column_dimensions["A"].width = 70
        err.column_dimensions["B"].width = 60

    wb.save(path)
    return path


def to_google_sheet(products: list[Product], sheet_id: str, credentials: str, worksheet: str = "Товары") -> str:
    """Записывает товары в Google Таблицу через сервисный аккаунт. Нужен пакет gspread."""
    try:
        import gspread
    except ImportError as error:
        raise RuntimeError("Для Google Таблиц установите gspread: pip install gspread") from error

    client = gspread.service_account(filename=credentials)
    book = client.open_by_key(sheet_id)
    try:
        sheet = book.worksheet(worksheet)
        sheet.clear()
    except gspread.WorksheetNotFound:
        sheet = book.add_worksheet(worksheet, rows=len(products) + 1, cols=len(Product.columns()))
    rows = [[COLUMN_TITLES[c] for c in Product.columns()]]
    for product in products:
        row = _row(product)
        rows.append(["" if row[c] is None else row[c] for c in Product.columns()])
    sheet.update(rows, "A1")
    sheet.freeze(rows=1)
    return book.url
