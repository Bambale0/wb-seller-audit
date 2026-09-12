from __future__ import annotations

from typing import Any

from app.models import SourceCapabilities, WbPublicProduct, WbPublicSnapshot
from app.services.classifier import keyword_classify


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    number = _number(value)
    if number is None:
        return None
    return int(number)


def _price_from_product(raw: dict[str, Any]) -> tuple[float | None, float | None]:
    sale_cents = _number(raw.get("salePriceU"))
    full_cents = _number(raw.get("priceU"))

    size_sale: list[float] = []
    size_full: list[float] = []
    for size in raw.get("sizes") or []:
        if not isinstance(size, dict):
            continue
        price = size.get("price")
        if not isinstance(price, dict):
            continue
        product = _number(price.get("product"))
        basic = _number(price.get("basic"))
        if product and product > 0:
            size_sale.append(product)
        if basic and basic > 0:
            size_full.append(basic)

    if sale_cents is None and size_sale:
        sale_cents = min(size_sale)
    if full_cents is None and size_full:
        full_cents = min(size_full)

    sale = round(sale_cents / 100, 2) if sale_cents is not None else None
    full = round(full_cents / 100, 2) if full_cents is not None else None
    return sale, full


def _quantity_from_product(raw: dict[str, Any]) -> int | None:
    direct = _int(raw.get("totalQuantity"))
    if direct is not None:
        return direct

    total = 0
    found = False
    for size in raw.get("sizes") or []:
        if not isinstance(size, dict):
            continue
        for stock in size.get("stocks") or []:
            if not isinstance(stock, dict):
                continue
            qty = _int(stock.get("qty"))
            if qty is None:
                continue
            total += qty
            found = True
    return total if found else None


def _products_from_page(page: dict[str, Any]) -> list[dict[str, Any]]:
    data = page.get("data")
    if isinstance(data, dict) and isinstance(data.get("products"), list):
        return [item for item in data["products"] if isinstance(item, dict)]
    if isinstance(page.get("products"), list):
        return [item for item in page["products"] if isinstance(item, dict)]
    return []


def build_wb_public_snapshot(
    pages: list[dict[str, Any]],
    seller_id: int,
) -> WbPublicSnapshot:
    items: list[WbPublicProduct] = []
    seen: set[int] = set()

    for page in pages:
        for raw in _products_from_page(page):
            nm_id = _int(raw.get("id") or raw.get("nmId") or raw.get("nmID"))
            if nm_id is None or nm_id in seen:
                continue

            raw_seller_id = _int(raw.get("supplierId") or raw.get("supplierID"))
            if raw_seller_id is not None and raw_seller_id != seller_id:
                continue

            name = str(raw.get("name") or raw.get("title") or "")
            classification = keyword_classify(name)
            price, full_price = _price_from_product(raw)

            items.append(
                WbPublicProduct(
                    nm_id=nm_id,
                    seller_id=raw_seller_id or seller_id,
                    seller_name=str(raw.get("supplier") or ""),
                    name=name,
                    brand=str(raw.get("brand") or ""),
                    price=price,
                    full_price=full_price,
                    total_quantity=_quantity_from_product(raw),
                    rating=_number(raw.get("reviewRating") or raw.get("rating")),
                    feedbacks=_int(raw.get("feedbacks")),
                    marked_candidate=classification.marked_candidate,
                    marked_confidence=classification.confidence,
                    marked_reason=classification.reason,
                )
            )
            seen.add(nm_id)

    marked = sum(item.marked_candidate for item in items)
    return WbPublicSnapshot(
        seller_id=seller_id,
        products=len(items),
        marked_candidates=marked,
        items=items,
        capabilities=SourceCapabilities(
            current_catalog=True,
            historical_sales=False,
            historical_revenue=False,
            tax_dates=False,
        ),
        notes=[
            "WB public даёт текущий каталог, цены и остатки, но не историю продаж.",
            "По этому источнику нельзя вычислять дату превышения НПД или историческую выручку.",
            "Маркируемые товары определяются предварительно по названию; итоговая проверка — по ОКПД2/ТН ВЭД.",
            "Для налоговых выводов исторические продажи нужно дополнить официальными отчётами WB/Ozon или иным историческим источником.",
        ],
    )
