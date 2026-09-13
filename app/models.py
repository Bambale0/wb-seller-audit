from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


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
    risk_records: list[SaleRecord] = Field(default_factory=list)
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


class MpstatsSellerAuditRequest(BaseModel):
    seller_id: int = Field(gt=0)
    d1: date
    d2: date
    fbs: bool = True
    page_size: int = Field(default=1000, ge=1, le=5000)
    max_items: int | None = Field(default=None, ge=1)
    history_mode: Literal["none", "marked", "all"] = "marked"
    item_concurrency: int = Field(default=5, ge=1, le=10)
    npd_limit: float = Field(default=2_400_000, gt=0)
    vat_145_three_month_limit: float = Field(default=2_000_000, gt=0)
    marketplace_expense_ratio: float = Field(default=0.60, ge=0, le=1)
    marked_goods_start: date = date(2025, 3, 1)

    @model_validator(mode="after")
    def validate_period(self):
        if self.d2 < self.d1:
            raise ValueError("d2 must be greater than or equal to d1")
        return self


class MpstatsSellerAuditResult(BaseModel):
    source: str = "mpstats_api"
    seller_id: int
    d1: date
    d2: date
    items_total: int | None = None
    items_fetched: int
    item_histories_fetched: int
    item_history_failures: list[dict[str, Any]] = Field(default_factory=list)
    quota: dict[str, int] | None = None
    capabilities: SourceCapabilities
    audit: AuditResult
    warnings: list[str] = Field(default_factory=list)
