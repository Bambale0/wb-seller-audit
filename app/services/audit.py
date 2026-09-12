from __future__ import annotations

from collections import defaultdict
from datetime import date

from app.models import AuditRequest, AuditResult, MonthSummary, RollingWindow
from app.services.classifier import keyword_classify


def _month_key(value: date) -> str:
    return f"{value.year:04d}-{value.month:02d}"


def build_audit(req: AuditRequest) -> AuditResult:
    records = sorted(req.records, key=lambda x: x.date)

    monthly_raw: dict[str, dict[str, float]] = defaultdict(
        lambda: {"revenue": 0.0, "orders": 0, "sales": 0, "returns": 0}
    )
    cumulative = 0.0
    first_npd_limit_exceeded = None
    first_marked_candidate_sale = None
    marked_candidates: list[dict] = []

    for record in records:
        month = monthly_raw[_month_key(record.date)]
        month["revenue"] += record.revenue
        month["orders"] += record.orders
        month["sales"] += record.sales
        month["returns"] += record.returns

        cumulative += record.revenue
        if first_npd_limit_exceeded is None and cumulative > req.npd_limit:
            first_npd_limit_exceeded = record.date

        cls = keyword_classify(record.name)
        if cls.marked_candidate and record.date >= req.marked_goods_start:
            if first_marked_candidate_sale is None:
                first_marked_candidate_sale = record.date
            marked_candidates.append(
                {
                    "date": record.date.isoformat(),
                    "nm_id": record.nm_id,
                    "sku": record.sku,
                    "name": record.name,
                    "revenue": round(record.revenue, 2),
                    "confidence": cls.confidence,
                    "reason": cls.reason,
                }
            )

    risk_dates = [d for d in (first_marked_candidate_sale, first_npd_limit_exceeded) if d]
    earliest_risk_date = min(risk_dates) if risk_dates else None
    revenue_after_risk = (
        sum(r.revenue for r in records if earliest_risk_date and r.date >= earliest_risk_date)
        if earliest_risk_date
        else 0.0
    )

    months = sorted(monthly_raw)
    monthly: list[MonthSummary] = []
    for month in months:
        raw = monthly_raw[month]
        expenses = raw["revenue"] * req.marketplace_expense_ratio
        monthly.append(
            MonthSummary(
                month=month,
                revenue=round(raw["revenue"], 2),
                orders=int(raw["orders"]),
                sales=int(raw["sales"]),
                returns=int(raw["returns"]),
                estimated_marketplace_expenses=round(expenses, 2),
                estimated_margin_after_marketplace=round(raw["revenue"] - expenses, 2),
            )
        )

    windows: list[RollingWindow] = []
    for idx in range(2, len(months)):
        selected = months[idx - 2 : idx + 1]
        revenue = sum(monthly_raw[m]["revenue"] for m in selected)
        windows.append(
            RollingWindow(
                start_month=selected[0],
                end_month=selected[-1],
                revenue=round(revenue, 2),
                exceeds_limit=revenue > req.vat_145_three_month_limit,
            )
        )

    return AuditResult(
        records=len(records),
        total_revenue=round(sum(r.revenue for r in records), 2),
        first_marked_candidate_sale=first_marked_candidate_sale,
        first_npd_limit_exceeded=first_npd_limit_exceeded,
        earliest_risk_date=earliest_risk_date,
        revenue_after_earliest_risk=round(revenue_after_risk, 2),
        monthly=monthly,
        vat_145_windows=windows,
        marked_candidates=marked_candidates,
        notes=[
            "MPStats/браузерные данные — реконструкция; итоговые суммы сверяются с официальными отчетами WB/Ozon.",
            "Классификация маркируемых товаров предварительная и не заменяет проверку ОКПД2/ТН ВЭД.",
            "Расходы маркетплейса по коэффициенту — оценка, не подтвержденный расход без первичных документов.",
        ],
    )
