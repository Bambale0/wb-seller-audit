from datetime import date

from app.models import WbPublicProduct
from app.services.wb_evidence import build_product_evidence


def test_product_evidence_uses_exact_nm_reviews_and_card_marking():
    product = WbPublicProduct(
        nm_id=401698072,
        name="Гетры для фигурного катания",
        marked_candidate=True,
    )
    card = {
        "nm_id": 401698072,
        "imt_id": 395243328,
        "create_date": "2025-04-27T21:51:40.863151Z",
        "update_date": "2026-08-23T18:55:55.313429Z",
        "need_kiz": True,
    }
    feedback_payload = {
        "feedbackCount": 125,
        "feedbacks": [
            {"nmId": 999999999, "createdDate": "2025-03-01T00:00:00Z"},
            {"nmId": 401698072, "createdDate": "2025-07-09T14:24:45Z"},
            {"nmId": 401698072, "createdDate": "2026-09-06T14:21:31Z"},
        ],
    }
    price_history = [
        {"dt": 1782000000, "price": {"RUB": 162771}},
        {"dt": 1788652800, "price": {"RUB": 160260}},
    ]

    result = build_product_evidence(
        product,
        card=card,
        price_history=price_history,
        feedback_payload=feedback_payload,
        basket_host="basket-23.wbbasket.ru",
    )

    assert result.card_created == date(2025, 4, 27)
    assert result.need_kiz is True
    assert result.imt_id == 395243328
    assert result.earliest_observed_review == date(2025, 7, 9)
    assert result.latest_observed_review == date(2026, 9, 6)
    assert result.exact_reviews_observed == 2
    assert result.group_feedback_count == 125
    assert result.price_history_from == date(2026, 6, 21)
    assert result.price_history_to == date(2026, 9, 6)
    assert result.price_history_points == 2
    assert result.basket_host == "basket-23.wbbasket.ru"


def test_product_evidence_does_not_claim_sale_without_exact_review():
    product = WbPublicProduct(
        nm_id=1,
        name="Гетры",
        marked_candidate=True,
    )

    result = build_product_evidence(
        product,
        card={"nm_id": 1, "create_date": "2025-04-01T00:00:00Z"},
        price_history=[],
        feedback_payload={
            "feedbackCount": 10,
            "feedbacks": [{"nmId": 2, "createdDate": "2025-04-02T00:00:00Z"}],
        },
        basket_host="basket-01.wbbasket.ru",
    )

    assert result.card_created == date(2025, 4, 1)
    assert result.earliest_observed_review is None
    assert result.exact_reviews_observed == 0
    assert result.need_kiz is None
