from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime
from typing import Any

from dateutil import parser as date_parser

from app.models import SaleRecord

DATE_KEYS = (
    "date",
    "dt",
    "day",
    "period",
    "data",
    "saleDate",
    "sale_date",
    "lastChangeDate",
    "orderDate",
)
NAME_KEYS = ("name", "title", "productName", "product_name", "subjectName", "subject_name")
NM_KEYS = ("nmId", "nm_id", "nmID", "article", "wbArticle", "id")
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


def _payload_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("data", "items", "rows", "result"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    return []


def normalize_mpstats_seller_by_date(
    payload: Any,
    *,
    seller_id: int,
) -> list[SaleRecord]:
    records: list[SaleRecord] = []
    for row in _payload_rows(payload):
        dt = _date(_first(row, DATE_KEYS))
        if dt is None:
            continue

        records.append(
            SaleRecord(
                date=dt,
                seller_id=seller_id,
                sales=_int(_first(row, SALES_KEYS)),
                revenue=_number(_first(row, REVENUE_KEYS)),
            )
        )

    return sorted(records, key=lambda record: record.date)


def normalize_mpstats_item_history(
    item: dict[str, Any],
    payload: Any,
    *,
    seller_id: int,
    include_fbs: bool,
) -> list[SaleRecord]:
    raw_id = item.get("id") or item.get("nm_id") or item.get("nmId")
    try:
        nm_id = int(raw_id)
    except (TypeError, ValueError):
        nm_id = None

    name = str(item.get("name") or item.get("title") or "")
    sku = str(
        item.get("supplierArticle")
        or item.get("vendorCode")
        or item.get("vendor_code")
        or ""
    ) or None

    records: list[SaleRecord] = []
    for row in _payload_rows(payload):
        dt = _date(_first(row, DATE_KEYS))
        if dt is None:
            continue

        sales = _int(_first(row, SALES_KEYS))
        if include_fbs:
            sales += _int(row.get("salesfbs") or row.get("sales_fbs"))

        revenue = _number(_first(row, REVENUE_KEYS))
        if revenue == 0 and sales > 0:
            price = _number(
                row.get("final_price")
                or row.get("client_price")
                or row.get("price")
            )
            if price > 0:
                revenue = sales * price

        records.append(
            SaleRecord(
                date=dt,
                seller_id=seller_id,
                nm_id=nm_id,
                sku=sku,
                name=name,
                sales=sales,
                returns=_int(_first(row, RETURNS_KEYS)),
                revenue=revenue,
            )
        )

    return sorted(records, key=lambda record: record.date)
