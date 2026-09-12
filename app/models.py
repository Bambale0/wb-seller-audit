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
