from __future__ import annotations

from collections import defaultdict
from datetime import date

from app.models import AuditRequest, AuditResult, MonthSummary, RollingWindow
from app.services.classifier import keyword_classify


def _month_key(value: date) -> str:
    return f"{value.year:04d}-{value.month:02d}"


def _next_month(month: str) -> str:
    year, value = map(int, month.split("-"))
    value += 1
    if value == 13:
        year += 1
        value = 1
    return f"{year:04d}-{value:02d}"


def _continuous_months(start: str, end: str) -> list[str]:
    result = []
    current = start
    while current <= end:
        result.append(current)
        current = _next_month(current)
    return result


def _has_sale_activity(record) -> bool:
    return any(
        (
            record.revenue > 0,
            record.sales > 0,
            record.orders > 0,
        )
    )


def build_audit(req: AuditRequest) -> AuditResult:
    records = sorted(req.records, key=lambda x: x.date)

    monthly_raw: dict[str, dict[str, float]] = defaultdict(
        lambda: {"revenue": 0.0, "orders": 0, "sales": 0, "returns": 0}
    )
    cumulative_by_year: dict[int, float] = defaultdict(float)
    npd_limit_exceeded_by_year: dict[str, date] = {}

    for record in records:
        month = monthly_raw[_month_key(record.date)]
        month["revenue"] += record.revenue
        month["orders"] += record.orders
        month["sales"] += record.sales
        month["returns"] += record.returns

        cumulative_by_year[record.date.year] += record.revenue
        year_key = str(record.date.year)
        if (
            year_key not in npd_limit_exceeded_by_year
            and cumulative_by_year[record.date.year] > req.npd_limit
        ):
            npd_limit_exceeded_by_year[year_key] = record.date

    risk_records = sorted(req.risk_records or records, key=lambda x: x.date)
    first_marked_candidate_sale = None
    marked_candidates: list[dict] = []

    for record in risk_records:
        cls = keyword_classify(record.name)
        if (
            cls.marked_candidate
            and record.date >= req.marked_goods_start
            and _has_sale_activity(record)
        ):
            if first_marked_candidate_sale is None:
                first_marked_candidate_sale = record.date
            marked_candidates.append(
                {
                    "date": record.date.isoformat(),
                    "nm_id": record.nm_id,
                    "sku": record.sku,
                    "name": record.name,
                    "revenue": round(record.revenue, 2),
                    "sales": record.sales,
                    "confidence": cls.confidence,
                    "reason": cls.reason,
                }
            )

    first_npd_limit_exceeded = (
        min(npd_limit_exceeded_by_year.values())
        if npd_limit_exceeded_by_year
        else None
    )
    risk_dates = [d for d in (first_marked_candidate_sale, first_npd_limit_exceeded) if d]
    earliest_risk_date = min(risk_dates) if risk_dates else None
    revenue_after_risk = (
        sum(r.revenue for r in records if earliest_risk_date and r.date >= earliest_risk_date)
        if earliest_risk_date
        else 0.0
    )

    actual_months = sorted(monthly_raw)
    months = (
        _continuous_months(actual_months[0], actual_months[-1])
        if actual_months
        else []
    )
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
        npd_limit_exceeded_by_year=npd_limit_exceeded_by_year,
        earliest_risk_date=earliest_risk_date,
        revenue_after_earliest_risk=round(revenue_after_risk, 2),
        monthly=monthly,
        vat_145_windows=windows,
        marked_candidates=marked_candidates,
        notes=[
            "Лимит НПД 2,4 млн ₽ проверяется отдельно по каждому календарному году.",
            "MPStats/браузерные данные — реконструкция; итоговые суммы сверяются с официальными отчетами WB/Ozon.",
            "Классификация маркируемых товаров предварительная и не заменяет проверку ОКПД2/ТН ВЭД.",
            "Расходы маркетплейса по коэффициенту — оценка, не подтвержденный расход без первичных документов.",
        ],
    )
