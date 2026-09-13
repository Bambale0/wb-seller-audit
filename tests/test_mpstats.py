import json
from datetime import date

import httpx
import pytest

from app.models import MpstatsSellerAuditRequest
from app.services.mpstats import (
    MpstatsClient,
    build_mpstats_audit_from_payloads,
)


class SellerItemsTransport(httpx.AsyncBaseTransport):
    def __init__(self):
        self.requests = []
        self.first_page_attempts = 0

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)

        if request.url.path.endswith("/seller/items"):
            body = json.loads(request.content.decode())
            start = body["startRow"]

            if start == 0:
                self.first_page_attempts += 1
                if self.first_page_attempts == 1:
                    return httpx.Response(
                        429,
                        headers={"Retry-After": "0"},
                        json={"message": "slow down"},
                    )
                return httpx.Response(
                    200,
                    json={
                        "total": 3,
                        "data": [
                            {"id": 1, "name": "A", "revenue": 100},
                            {"id": 2, "name": "B", "revenue": 90},
                        ],
                    },
                )

            return httpx.Response(
                200,
                json={
                    "total": 3,
                    "data": [{"id": 3, "name": "C", "revenue": 80}],
                },
            )

        raise AssertionError(f"Unexpected request: {request.method} {request.url}")


@pytest.mark.asyncio
async def test_mpstats_client_retries_rate_limit_and_paginates():
    transport = SellerItemsTransport()
    async with MpstatsClient(
        token="test-token",
        transport=transport,
        max_retries=1,
        retry_base_seconds=0,
    ) as client:
        items, total = await client.seller_items(
            seller_id=739228,
            d1=date(2025, 1, 1),
            d2=date(2025, 12, 31),
            fbs=True,
            page_size=2,
        )

    assert total == 3
    assert [item["id"] for item in items] == [1, 2, 3]
    assert transport.first_page_attempts == 2
    assert all(
        request.headers["X-Mpstats-TOKEN"] == "test-token"
        for request in transport.requests
    )


def test_mpstats_payload_audit_uses_seller_revenue_and_sku_history_separately():
    request = MpstatsSellerAuditRequest(
        seller_id=739228,
        d1=date(2025, 5, 1),
        d2=date(2025, 5, 3),
        history_mode="marked",
        marketplace_expense_ratio=1 / 3,
    )
    items = [
        {
            "id": 101,
            "name": "Гетры спортивные",
            "revenue": 300,
        }
    ]
    seller_by_date = [
        {"period": "2025-05-01", "sales": 1, "revenue": 100},
        {"period": "2025-05-02", "sales": 2, "revenue": 200},
        {"period": "2025-05-03", "sales": 0, "revenue": 0},
    ]
    item_histories = {
        101: [
            {"date": "2025-05-01", "sales": 0, "final_price": 150},
            {"date": "2025-05-02", "sales": 1, "final_price": 150},
        ]
    }

    result = build_mpstats_audit_from_payloads(
        request,
        items=items,
        seller_by_date=seller_by_date,
        item_histories=item_histories,
        quota={"available": 100, "used": 3, "remaining": 97},
        items_total=1,
    )

    assert result.source == "mpstats_api"
    assert result.audit.total_revenue == 300
    assert result.audit.records == 3
    assert result.audit.first_marked_candidate_sale == date(2025, 5, 2)
    assert result.audit.earliest_risk_date == date(2025, 5, 2)
    assert result.audit.monthly[0].revenue == 300
    assert result.item_histories_fetched == 1
    assert result.quota["remaining"] == 97
