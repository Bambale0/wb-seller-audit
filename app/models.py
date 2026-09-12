from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field


class SaleRecord(BaseModel):
    date: date
    seller_id: int | None = None
    nm_id: int | None = None
    sku: str | None = None
    name: str = ""
    orders: int = 0
    sales: int = 0
    returns: int = 0
    revenue: float = 0.0


class AuditRequest(BaseModel):
    records: list[SaleRecord]
    npd_limit: float = 2_400_000
    vat_145_three_month_limit: float = 2_000_000
    marketplace_expense_ratio: float = Field(default=0.60, ge=0, le=1)
    marked_goods_start: date = date(2025, 3, 1)


class CapturesRequest(BaseModel):
    captures: list[dict[str, Any]]
    seller_id: int | None = None


class WbPublicCatalogRequest(BaseModel):
    seller_id: int = Field(gt=0)
    pages: list[dict[str, Any]] = Field(min_length=1)


class WbPublicEvidenceRequest(WbPublicCatalogRequest):
    marked_only: bool = True
    max_items: int = Field(default=30, ge=1, le=100)


class ClassificationRequest(BaseModel):
    names: list[str] = Field(min_length=1, max_length=30)


class Classification(BaseModel):
    category: str
    marked_candidate: bool
    confidence: float
    reason: str


class MonthSummary(BaseModel):
    month: str
    revenue: float
    orders: int
    sales: int
    returns: int
    estimated_marketplace_expenses: float
    estimated_margin_after_marketplace: float


class RollingWindow(BaseModel):
    start_month: str
    end_month: str
    revenue: float
    exceeds_limit: bool


class AuditResult(BaseModel):
    records: int
    total_revenue: float
    first_marked_candidate_sale: date | None
    first_npd_limit_exceeded: date | None
    npd_limit_exceeded_by_year: dict[str, date]
    earliest_risk_date: date | None
    revenue_after_earliest_risk: float
    monthly: list[MonthSummary]
    vat_145_windows: list[RollingWindow]
    marked_candidates: list[dict[str, Any]]
    notes: list[str]


class WbPublicProduct(BaseModel):
    nm_id: int
    seller_id: int | None = None
    seller_name: str = ""
    name: str = ""
    brand: str = ""
    price: float | None = None
    full_price: float | None = None
    total_quantity: int | None = None
    rating: float | None = None
    feedbacks: int | None = None
    marked_candidate: bool = False
    marked_confidence: float = 0.0
    marked_reason: str = ""


class SourceCapabilities(BaseModel):
    current_catalog: bool
    historical_sales: bool
    historical_revenue: bool
    tax_dates: bool


class WbPublicSnapshot(BaseModel):
    source: str = "wb_public"
    seller_id: int
    products: int
    marked_candidates: int
    items: list[WbPublicProduct]
    capabilities: SourceCapabilities
    notes: list[str]


class WbPriceHistoryPoint(BaseModel):
    date: date
    price_rub: float


class WbProductEvidence(BaseModel):
    nm_id: int
    name: str
    marked_candidate: bool
    imt_id: int | None = None
    card_created: date | None = None
    card_updated: date | None = None
    need_kiz: bool | None = None
    price_history_from: date | None = None
    price_history_to: date | None = None
    price_history_points: int = 0
    earliest_observed_review: date | None = None
    latest_observed_review: date | None = None
    exact_reviews_observed: int = 0
    group_feedback_count: int | None = None
    basket_host: str | None = None
    notes: list[str] = Field(default_factory=list)


class WbEvidenceResult(BaseModel):
    source: str = "wb_public_evidence"
    seller_id: int
    scanned_products: int
    marked_products_scanned: int
    wb_need_kiz_true: int
    earliest_marked_card_created: date | None
    earliest_marked_observed_review: date | None
    items: list[WbProductEvidence]
    notes: list[str]
