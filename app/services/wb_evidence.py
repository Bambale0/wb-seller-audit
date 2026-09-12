from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from typing import Any

import httpx

from app.models import (
    WbEvidenceResult,
    WbProductEvidence,
    WbPublicEvidenceRequest,
    WbPublicProduct,
)
from app.services.wb_public import build_wb_public_snapshot

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
}

_FEEDBACK_HOST_RESOLVER = "https://feedback-bt.wildberries.ru/feedback/api/v2/host"

# Current public CDN snapshot. We still probe around the guess and then all
# baskets because WB periodically shifts vol ranges.
_BASKET_RANGES = (
    (143, 1),
    (287, 2),
    (431, 3),
    (719, 4),
    (1007, 5),
    (1061, 6),
    (1115, 7),
    (1169, 8),
    (1313, 9),
    (1601, 10),
    (1655, 11),
    (1919, 12),
    (2045, 13),
    (2189, 14),
    (2405, 15),
    (2621, 16),
    (2837, 17),
    (3053, 18),
    (3269, 19),
    (3485, 20),
    (3701, 21),
    (3917, 22),
    (4133, 23),
    (4349, 24),
    (4565, 25),
    (4781, 26),
)


def _date(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None


def _price_history_points(payload: Any) -> list[tuple[date, float]]:
    result: list[tuple[date, float]] = []
    if not isinstance(payload, list):
        return result

    for point in payload:
        if not isinstance(point, dict):
            continue
        ts = point.get("dt")
        prices = point.get("price")
        if not isinstance(prices, dict):
            continue
        raw_price = prices.get("RUB")
        try:
            if isinstance(ts, str) and ts.isdigit():
                ts = int(ts)
            if not isinstance(ts, (int, float)):
                continue
            dt = datetime.fromtimestamp(ts, timezone.utc).date()
            price_rub = round(float(raw_price) / 100, 2)
        except (TypeError, ValueError, OSError, OverflowError):
            continue
        result.append((dt, price_rub))

    return sorted(result, key=lambda item: item[0])


def build_product_evidence(
    product: WbPublicProduct,
    *,
    card: dict[str, Any] | None,
    price_history: Any,
    feedback_payload: dict[str, Any] | None,
    basket_host: str | None,
) -> WbProductEvidence:
    card = card or {}
    feedback_payload = feedback_payload or {}
    points = _price_history_points(price_history)

    exact_feedbacks = []
    for feedback in feedback_payload.get("feedbacks") or []:
        if not isinstance(feedback, dict):
            continue
        try:
            nm_id = int(feedback.get("nmId"))
        except (TypeError, ValueError):
            continue
        if nm_id != product.nm_id:
            continue
        created = _date(feedback.get("createdDate"))
        if created is not None:
            exact_feedbacks.append(created)

    notes: list[str] = []
    if card.get("need_kiz") is True:
        notes.append("WB card.json сообщает need_kiz=true для этого артикула.")
    if exact_feedbacks:
        notes.append(
            "Публичный отзыв на конкретный nmId подтверждает выкуп не позднее даты отзыва; "
            "это доказательство наличия продажи, но не бухгалтерская первичка."
        )
    if points:
        notes.append(
            "price-history.json подтверждает историю публичной цены только в покрываемом WB периоде."
        )

    group_feedback_count = feedback_payload.get("feedbackCount")
    try:
        group_feedback_count = (
            int(group_feedback_count) if group_feedback_count is not None else None
        )
    except (TypeError, ValueError):
        group_feedback_count = None

    return WbProductEvidence(
        nm_id=product.nm_id,
        name=product.name,
        marked_candidate=product.marked_candidate,
        imt_id=card.get("imt_id"),
        card_created=_date(card.get("create_date")),
        card_updated=_date(card.get("update_date")),
        need_kiz=card.get("need_kiz") if isinstance(card.get("need_kiz"), bool) else None,
        price_history_from=points[0][0] if points else None,
        price_history_to=points[-1][0] if points else None,
        price_history_points=len(points),
        earliest_observed_review=min(exact_feedbacks) if exact_feedbacks else None,
        latest_observed_review=max(exact_feedbacks) if exact_feedbacks else None,
        exact_reviews_observed=len(exact_feedbacks),
        group_feedback_count=group_feedback_count,
        basket_host=basket_host,
        notes=notes,
    )


def _guess_basket(vol: int) -> int:
    for upper, basket in _BASKET_RANGES:
        if vol <= upper:
            return basket
    # New baskets are usually added in roughly similar vol bands. This is
    # only a first guess; _basket_candidates always falls back to all hosts.
    extra = max(0, vol - _BASKET_RANGES[-1][0] - 1)
    return min(60, 27 + (extra // 216))


def _basket_candidates(nm_id: int) -> list[str]:
    vol = nm_id // 100_000
    guess = _guess_basket(vol)
    preferred = [guess, guess - 1, guess + 1, guess - 2, guess + 2]
    ordered: list[int] = []
    for value in preferred + list(range(1, 61)):
        if 1 <= value <= 60 and value not in ordered:
            ordered.append(value)
    return [f"basket-{value:02d}.wbbasket.ru" for value in ordered]


class WbEvidenceCollector:
    def __init__(self, client: httpx.AsyncClient):
        self.client = client
        self._basket_host_by_vol: dict[int, str] = {}
        self._feedback_payload_by_imt: dict[int, dict[str, Any]] = {}

    async def _get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        retries: int = 2,
    ) -> Any:
        for attempt in range(retries + 1):
            try:
                response = await self.client.get(url, params=params)
            except httpx.HTTPError:
                response = None

            if response is not None and response.status_code == 200:
                try:
                    return response.json()
                except ValueError:
                    return None

            if response is not None and response.status_code not in {403, 429, 498, 500, 502, 503, 504}:
                return None

            if attempt < retries:
                await asyncio.sleep(0.5 * (attempt + 1))
        return None

    async def resolve_card(self, nm_id: int) -> tuple[str | None, dict[str, Any]]:
        vol = nm_id // 100_000
        part = nm_id // 1000

        cached = self._basket_host_by_vol.get(vol)
        hosts = [cached] if cached else []
        hosts += [host for host in _basket_candidates(nm_id) if host != cached]

        for host in hosts:
            url = f"https://{host}/vol{vol}/part{part}/{nm_id}/info/ru/card.json"
            payload = await self._get_json(url, retries=0)
            if isinstance(payload, dict) and payload.get("nm_id"):
                self._basket_host_by_vol[vol] = host
                return host, payload
        return None, {}

    async def price_history(self, nm_id: int, basket_host: str | None) -> Any:
        if not basket_host:
            return []
        vol = nm_id // 100_000
        part = nm_id // 1000
        url = (
            f"https://{basket_host}/vol{vol}/part{part}/{nm_id}/"
            "info/price-history.json"
        )
        payload = await self._get_json(url)
        return payload if isinstance(payload, list) else []

    async def feedback_payload(self, imt_id: int | None) -> dict[str, Any]:
        if not imt_id:
            return {}
        if imt_id in self._feedback_payload_by_imt:
            return self._feedback_payload_by_imt[imt_id]

        hosts = await self._get_json(
            _FEEDBACK_HOST_RESOLVER,
            params={"imt": imt_id},
        )
        candidates: list[str] = []
        if isinstance(hosts, list):
            candidates.extend(str(host).rstrip("/") for host in hosts if host)
        candidates.extend(["https://feedbacks1.wb.ru", "https://feedbacks2.wb.ru"])

        seen: set[str] = set()
        for base in candidates:
            if base in seen:
                continue
            seen.add(base)
            payload = await self._get_json(f"{base}/feedbacks/v2/{imt_id}")
            if isinstance(payload, dict) and "feedbacks" in payload:
                self._feedback_payload_by_imt[imt_id] = payload
                return payload

        self._feedback_payload_by_imt[imt_id] = {}
        return {}

    async def collect(self, product: WbPublicProduct) -> WbProductEvidence:
        host, card = await self.resolve_card(product.nm_id)
        imt_id = card.get("imt_id") if isinstance(card, dict) else None
        price_history, feedback_payload = await asyncio.gather(
            self.price_history(product.nm_id, host),
            self.feedback_payload(imt_id),
        )
        return build_product_evidence(
            product,
            card=card,
            price_history=price_history,
            feedback_payload=feedback_payload,
            basket_host=host,
        )


async def collect_wb_public_evidence(request: WbPublicEvidenceRequest) -> WbEvidenceResult:
    snapshot = build_wb_public_snapshot(request.pages, seller_id=request.seller_id)
    selected = [
        item
        for item in snapshot.items
        if item.marked_candidate or not request.marked_only
    ][: request.max_items]

    limits = httpx.Limits(max_connections=8, max_keepalive_connections=4)
    timeout = httpx.Timeout(20.0)
    async with httpx.AsyncClient(headers=_HEADERS, limits=limits, timeout=timeout) as client:
        collector = WbEvidenceCollector(client)
        semaphore = asyncio.Semaphore(4)

        async def one(product: WbPublicProduct) -> WbProductEvidence:
            async with semaphore:
                return await collector.collect(product)

        items = await asyncio.gather(*(one(product) for product in selected))

    marked_items = [item for item in items if item.marked_candidate]
    marked_card_dates = [
        item.card_created for item in marked_items if item.card_created is not None
    ]
    marked_review_dates = [
        item.earliest_observed_review
        for item in marked_items
        if item.earliest_observed_review is not None
    ]

    return WbEvidenceResult(
        seller_id=request.seller_id,
        scanned_products=len(items),
        marked_products_scanned=len(marked_items),
        wb_need_kiz_true=sum(item.need_kiz is True for item in marked_items),
        earliest_marked_card_created=min(marked_card_dates) if marked_card_dates else None,
        earliest_marked_observed_review=min(marked_review_dates) if marked_review_dates else None,
        items=items,
        notes=[
            "card.json create_date подтверждает существование карточки, но не факт продажи.",
            "WB официально разрешает отзыв только на выкупленный товар; дата публичного отзыва "
            "по конкретному nmId подтверждает, что выкуп произошёл не позднее этой даты.",
            "Публичная лента отзывов может быть неполной, поэтому earliest_observed_review — "
            "самая ранняя найденная дата, а не гарантированно первая продажа.",
            "price-history.json хранит только доступный WB диапазон истории цены и не содержит количество продаж.",
            "Этот слой уточняет даты и маркировку, но не заменяет официальные отчёты WB/Ozon для расчёта выручки.",
        ],
    )
