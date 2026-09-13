from __future__ import annotations

import asyncio
import os
from collections.abc import Iterable
from datetime import date
from typing import Any

import httpx

from app.models import (
    AuditRequest,
    MpstatsSellerAuditRequest,
    MpstatsSellerAuditResult,
    SourceCapabilities,
)
from app.services.audit import build_audit
from app.services.classifier import keyword_classify
from app.services.normalizer import (
    normalize_mpstats_item_history,
    normalize_mpstats_seller_by_date,
)


class MpstatsError(RuntimeError):
    pass


class MpstatsNotConfigured(MpstatsError):
    pass


class MpstatsAuthError(MpstatsError):
    pass


class MpstatsClient:
    def __init__(
        self,
        token: str | None = None,
        *,
        base_url: str | None = None,
        root_url: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        retry_base_seconds: float | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.token = token or os.getenv("MPSTATS_TOKEN", "")
        if not self.token:
            raise MpstatsNotConfigured("MPSTATS_TOKEN is not configured")

        self.base_url = (
            base_url
            or os.getenv("MPSTATS_API_BASE_URL")
            or "https://mpstats.io/api/analytics/v1/wb"
        ).rstrip("/")
        self.root_url = (
            root_url
            or os.getenv("MPSTATS_API_ROOT_URL")
            or "https://mpstats.io/api"
        ).rstrip("/")
        self.timeout = timeout or float(os.getenv("MPSTATS_TIMEOUT_SECONDS", "30"))
        self.max_retries = (
            max_retries
            if max_retries is not None
            else int(os.getenv("MPSTATS_MAX_RETRIES", "4"))
        )
        self.retry_base_seconds = (
            retry_base_seconds
            if retry_base_seconds is not None
            else float(os.getenv("MPSTATS_RETRY_BASE_SECONDS", "1"))
        )
        self._client = httpx.AsyncClient(
            timeout=self.timeout,
            transport=transport,
            headers={
                "X-Mpstats-TOKEN": self.token,
                "Content-Type": "application/json",
            },
        )

    async def __aenter__(self) -> "MpstatsClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        root: bool = False,
    ) -> Any:
        base = self.root_url if root else self.base_url
        url = f"{base}/{path.lstrip('/')}"

        last_message = ""
        for attempt in range(self.max_retries + 1):
            response = await self._client.request(
                method,
                url,
                params=params,
                json=json_body,
            )

            if response.status_code == 200:
                try:
                    return response.json()
                except ValueError as exc:
                    raise MpstatsError("MPStats returned invalid JSON") from exc

            try:
                payload = response.json()
                last_message = str(payload.get("message") or payload)
            except ValueError:
                last_message = response.text[:500]

            if response.status_code == 401:
                raise MpstatsAuthError(
                    f"MPStats rejected API token: {last_message or 'HTTP 401'}"
                )

            retryable = response.status_code in {202, 429, 500, 502, 503, 504}
            if not retryable or attempt >= self.max_retries:
                raise MpstatsError(
                    f"MPStats HTTP {response.status_code}: {last_message or 'request failed'}"
                )

            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    delay = max(0.0, float(retry_after))
                except ValueError:
                    delay = self.retry_base_seconds * (2**attempt)
            else:
                delay = self.retry_base_seconds * (2**attempt)

            await asyncio.sleep(min(delay, 30.0))

        raise MpstatsError(last_message or "MPStats request failed")

    async def account_limits(self) -> dict[str, int]:
        payload = await self._request_json(
            "GET",
            "user/report_api_limit",
            root=True,
        )
        if not isinstance(payload, dict):
            raise MpstatsError("Unexpected MPStats API limit response")
        available = int(payload.get("available") or 0)
        used = int(payload.get("use") or 0)
        return {
            "available": available,
            "used": used,
            "remaining": max(0, available - used),
        }

    async def seller_items(
        self,
        *,
        seller_id: int,
        d1: date,
        d2: date,
        fbs: bool,
        page_size: int = 1000,
        max_items: int | None = None,
    ) -> tuple[list[dict[str, Any]], int | None]:
        start = 0
        items: list[dict[str, Any]] = []
        total: int | None = None
        seen: set[int] = set()

        while True:
            end = start + page_size
            payload = await self._request_json(
                "POST",
                "seller/items",
                params={
                    "d1": d1.isoformat(),
                    "d2": d2.isoformat(),
                    "path": seller_id,
                    "fbs": int(fbs),
                },
                json_body={
                    "startRow": start,
                    "endRow": end,
                    "filterModel": {},
                    "sortModel": [{"colId": "revenue", "sort": "desc"}],
                },
            )

            if isinstance(payload, dict):
                raw_rows = payload.get("data")
                if total is None and payload.get("total") is not None:
                    try:
                        total = int(payload["total"])
                    except (TypeError, ValueError):
                        total = None
            elif isinstance(payload, list):
                raw_rows = payload
            else:
                raise MpstatsError("Unexpected seller/items response")

            rows = [row for row in (raw_rows or []) if isinstance(row, dict)]
            for row in rows:
                raw_id = row.get("id") or row.get("nm_id") or row.get("nmId")
                try:
                    item_id = int(raw_id)
                except (TypeError, ValueError):
                    item_id = None

                if item_id is not None:
                    if item_id in seen:
                        continue
                    seen.add(item_id)

                items.append(row)
                if max_items is not None and len(items) >= max_items:
                    return items[:max_items], total

            if not rows:
                break

            start += len(rows)
            if total is not None and start >= total:
                break
            if len(rows) < page_size:
                break

        return items, total

    async def seller_by_date(
        self,
        *,
        seller_id: int,
        d1: date,
        d2: date,
        fbs: bool,
    ) -> Any:
        return await self._request_json(
            "POST",
            "seller/by_date",
            params={
                "d1": d1.isoformat(),
                "d2": d2.isoformat(),
                "path": seller_id,
                "fbs": int(fbs),
            },
        )

    async def item_by_period(
        self,
        *,
        nm_id: int,
        d1: date,
        d2: date,
        fbs: bool,
    ) -> Any:
        return await self._request_json(
            "GET",
            f"items/{nm_id}/by_period",
            params={
                "d1": d1.isoformat(),
                "d2": d2.isoformat(),
                "fbs": int(fbs),
            },
        )


def _candidate_items(
    items: Iterable[dict[str, Any]],
    history_mode: str,
) -> list[dict[str, Any]]:
    if history_mode == "none":
        return []
    if history_mode == "all":
        return list(items)

    result: list[dict[str, Any]] = []
    for item in items:
        name = str(item.get("name") or item.get("title") or "")
        if keyword_classify(name).marked_candidate:
            result.append(item)
    return result


def build_mpstats_audit_from_payloads(
    request: MpstatsSellerAuditRequest,
    *,
    items: list[dict[str, Any]],
    seller_by_date: Any,
    item_histories: dict[int, Any],
    quota: dict[str, int] | None = None,
    item_history_failures: list[dict[str, Any]] | None = None,
    items_total: int | None = None,
) -> MpstatsSellerAuditResult:
    seller_records = normalize_mpstats_seller_by_date(
        seller_by_date,
        seller_id=request.seller_id,
    )

    risk_records = []
    for item in items:
        raw_id = item.get("id") or item.get("nm_id") or item.get("nmId")
        try:
            nm_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        history = item_histories.get(nm_id)
        if history is None:
            continue
        risk_records.extend(
            normalize_mpstats_item_history(
                item,
                history,
                seller_id=request.seller_id,
                include_fbs=request.fbs,
            )
        )

    audit = build_audit(
        AuditRequest(
            records=seller_records,
            risk_records=risk_records,
            npd_limit=request.npd_limit,
            vat_145_three_month_limit=request.vat_145_three_month_limit,
            marketplace_expense_ratio=request.marketplace_expense_ratio,
            marked_goods_start=request.marked_goods_start,
        )
    )

    warnings: list[str] = []
    item_revenue = sum(float(item.get("revenue") or 0) for item in items)
    seller_revenue = audit.total_revenue
    if item_revenue > 0 and seller_revenue > 0:
        delta = abs(item_revenue - seller_revenue) / max(item_revenue, seller_revenue)
        if delta > 0.05:
            warnings.append(
                "Сумма revenue по seller/items отличается от seller/by_date более чем на 5%; "
                "проверь период, FBS и полноту пагинации."
            )

    if not seller_records:
        warnings.append(
            "MPStats seller/by_date не вернул дневную историю; даты лимитов по выручке не вычисляются."
        )
    if request.history_mode != "none" and not risk_records:
        warnings.append(
            "SKU-level history не получена; дата первой продажи маркируемого товара может быть не определена."
        )

    failures = item_history_failures or []
    if failures:
        warnings.append(
            f"Не удалось получить историю для {len(failures)} SKU; аудит выполнен по доступным данным."
        )

    return MpstatsSellerAuditResult(
        seller_id=request.seller_id,
        d1=request.d1,
        d2=request.d2,
        items_total=items_total,
        items_fetched=len(items),
        item_histories_fetched=len(item_histories),
        item_history_failures=failures,
        quota=quota,
        capabilities=SourceCapabilities(
            current_catalog=True,
            historical_sales=True,
            historical_revenue=True,
            tax_dates=True,
        ),
        audit=audit,
        warnings=warnings,
    )


async def fetch_and_build_mpstats_seller_audit(
    request: MpstatsSellerAuditRequest,
    *,
    client: MpstatsClient | None = None,
) -> MpstatsSellerAuditResult:
    owns_client = client is None
    mpstats = client or MpstatsClient()

    try:
        items_task = asyncio.create_task(
            mpstats.seller_items(
                seller_id=request.seller_id,
                d1=request.d1,
                d2=request.d2,
                fbs=request.fbs,
                page_size=request.page_size,
                max_items=request.max_items,
            )
        )
        by_date_task = asyncio.create_task(
            mpstats.seller_by_date(
                seller_id=request.seller_id,
                d1=request.d1,
                d2=request.d2,
                fbs=request.fbs,
            )
        )
        quota_task = asyncio.create_task(mpstats.account_limits())

        (items, items_total), seller_daily = await asyncio.gather(
            items_task,
            by_date_task,
        )

        try:
            quota = await quota_task
        except MpstatsError:
            quota = None

        history_items = _candidate_items(items, request.history_mode)
        semaphore = asyncio.Semaphore(request.item_concurrency)
        item_histories: dict[int, Any] = {}
        failures: list[dict[str, Any]] = []

        async def fetch_history(item: dict[str, Any]) -> None:
            raw_id = item.get("id") or item.get("nm_id") or item.get("nmId")
            try:
                nm_id = int(raw_id)
            except (TypeError, ValueError):
                return

            async with semaphore:
                try:
                    item_histories[nm_id] = await mpstats.item_by_period(
                        nm_id=nm_id,
                        d1=request.d1,
                        d2=request.d2,
                        fbs=request.fbs,
                    )
                except MpstatsError as exc:
                    failures.append({"nm_id": nm_id, "error": str(exc)})

        await asyncio.gather(*(fetch_history(item) for item in history_items))

        return build_mpstats_audit_from_payloads(
            request,
            items=items,
            seller_by_date=seller_daily,
            item_histories=item_histories,
            quota=quota,
            item_history_failures=failures,
            items_total=items_total,
        )
    finally:
        if owns_client:
            await mpstats.aclose()
