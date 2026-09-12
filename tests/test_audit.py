from datetime import date

from app.models import AuditRequest, SaleRecord
from app.services.audit import build_audit


def test_audit_finds_marked_sale_and_annual_npd_limit():
    records = [
        SaleRecord(date=date(2025, 3, 10), name="Гетры спортивные", revenue=100_000),
        SaleRecord(date=date(2026, 6, 1), name="Шарф", revenue=2_200_000),
        SaleRecord(date=date(2026, 6, 20), name="Шарф", revenue=200_001),
    ]
    result = build_audit(AuditRequest(records=records))
    assert result.first_marked_candidate_sale == date(2025, 3, 10)
    assert result.first_npd_limit_exceeded == date(2026, 6, 20)
    assert result.npd_limit_exceeded_by_year == {"2026": date(2026, 6, 20)}
    assert result.earliest_risk_date == date(2025, 3, 10)


def test_npd_limit_resets_each_calendar_year():
    records = [
        SaleRecord(date=date(2025, 12, 31), name="A", revenue=2_300_000),
        SaleRecord(date=date(2026, 1, 1), name="A", revenue=200_000),
    ]
    result = build_audit(AuditRequest(records=records))
    assert result.first_npd_limit_exceeded is None
    assert result.npd_limit_exceeded_by_year == {}


def test_three_month_window_is_contiguous_and_fills_zero_months():
    records = [
        SaleRecord(date=date(2026, 1, 1), name="A", revenue=1_500_000),
        SaleRecord(date=date(2026, 3, 1), name="A", revenue=600_000),
    ]
    result = build_audit(AuditRequest(records=records))
    assert [m.month for m in result.monthly] == ["2026-01", "2026-02", "2026-03"]
    assert result.monthly[1].revenue == 0
    assert len(result.vat_145_windows) == 1
    assert result.vat_145_windows[0].revenue == 2_100_000
    assert result.vat_145_windows[0].exceeds_limit is True
