from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime
from typing import Any

from dateutil import parser as date_parser

from app.models import SaleRecord

DATE_KEYS = ("date", "dt", "day", "saleDate", "sale_date", "lastChangeDate", "orderDate")
NAME_KEYS = ("name", "title", "productName", "product_name", "subjectName", "subject_name")
NM_KEYS = ("nmId", "nm_id", "nmID", "article", "wbArticle")
SKU_KEYS = ("sku", "vendorCode", "vendor_code", "supplierArticle")
REVENUE_KEYS = ("revenue", "salesRub", "sales_rub", "saleSum", "sale_sum", "sum", "forPay", "retailAmount")
ORDERS_KEYS = ("orders", "ordersCount", "orders_count")
SALES_KEYS = ("sales", "salesCount", "sales_count", "quantity", "qty")
RETURNS_KEYS = ("returns", "returnsCount", "returns_count")


def _first(d: dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in d and d[key] not in (None, ""):
            return d[key]
    return None


def _number(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(" ", "").replace(",", "."))
    except (TypeError, ValueError):
        return default


def _int(value: Any) -> int:
    return int(round(_number(value)))


def _date(value: Any) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if not value:
        return None
    try:
        return date_parser.parse(str(value)).date()
    except (ValueError, TypeError, OverflowError):
        return None


def candidate_lists(value: Any):
    if isinstance(value, list):
        if value and sum(isinstance(x, dict) for x in value) >= max(1, len(value) // 2):
            yield value
        for item in value:
            yield from candidate_lists(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from candidate_lists(item)


def normalize_item(item: dict[str, Any], seller_id: int | None = None) -> SaleRecord | None:
    dt = _date(_first(item, DATE_KEYS))
    if dt is None:
        return None

    name = str(_first(item, NAME_KEYS) or "")
    nm_raw = _first(item, NM_KEYS)
    nm_id = None
    if nm_raw not in (None, ""):
        try:
            nm_id = int(str(nm_raw).strip())
        except ValueError:
            pass

    revenue = _number(_first(item, REVENUE_KEYS))
    orders = _int(_first(item, ORDERS_KEYS))
    sales = _int(_first(item, SALES_KEYS))
    returns = _int(_first(item, RETURNS_KEYS))

    if not any((name, nm_id, revenue, orders, sales, returns)):
        return None

    return SaleRecord(
        date=dt,
        seller_id=seller_id,
        nm_id=nm_id,
        sku=str(_first(item, SKU_KEYS) or "") or None,
        name=name,
        orders=orders,
        sales=sales,
        returns=returns,
        revenue=revenue,
    )


def normalize_captures(captures: list[dict[str, Any]], seller_id: int | None = None) -> list[SaleRecord]:
    records: list[SaleRecord] = []
    seen: set[tuple[Any, ...]] = set()

    for capture in captures:
        payload = capture.get("body", capture)
        for items in candidate_lists(payload):
            for item in items:
                if not isinstance(item, dict):
                    continue
                record = normalize_item(item, seller_id=seller_id)
                if record is None:
                    continue
                key = (
                    record.date,
                    record.nm_id,
                    record.sku,
                    record.name,
                    round(record.revenue, 2),
                    record.orders,
                    record.sales,
                    record.returns,
                )
                if key in seen:
                    continue
                seen.add(key)
                records.append(record)

    return sorted(records, key=lambda x: x.date)
