from app.services.wb_public import build_wb_public_snapshot


def test_public_wb_snapshot_collects_catalog_without_inventing_history():
    pages = [
        {
            "data": {
                "products": [
                    {
                        "id": 101,
                        "supplierId": 739228,
                        "supplier": "Seller",
                        "name": "Гетры спортивные",
                        "brand": "Brand",
                        "salePriceU": 15_900,
                        "priceU": 19_900,
                        "totalQuantity": 12,
                        "reviewRating": 4.8,
                        "feedbacks": 17,
                    },
                    {
                        "id": 102,
                        "supplierId": 739228,
                        "supplier": "Seller",
                        "name": "Шарф",
                        "brand": "Brand",
                        "sizes": [
                            {
                                "price": {"product": 12_500, "basic": 16_000},
                                "stocks": [{"qty": 3}, {"qty": 4}],
                            }
                        ],
                        "rating": 4.5,
                    },
                ]
            }
        },
        {
            "products": [
                {
                    "id": 101,
                    "supplierId": 739228,
                    "name": "Гетры спортивные",
                    "salePriceU": 15_900,
                }
            ]
        },
    ]

    result = build_wb_public_snapshot(pages, seller_id=739228)

    assert result.source == "wb_public"
    assert result.products == 2
    assert result.marked_candidates == 1
    assert result.capabilities.current_catalog is True
    assert result.capabilities.historical_sales is False
    assert result.capabilities.historical_revenue is False
    assert result.capabilities.tax_dates is False

    by_id = {item.nm_id: item for item in result.items}
    assert by_id[101].price == 159
    assert by_id[101].full_price == 199
    assert by_id[101].marked_candidate is True
    assert by_id[102].price == 125
    assert by_id[102].full_price == 160
    assert by_id[102].total_quantity == 7


def test_public_wb_snapshot_ignores_products_from_another_seller():
    pages = [
        {
            "data": {
                "products": [
                    {"id": 1, "supplierId": 739228, "name": "Гамаши"},
                    {"id": 2, "supplierId": 999999, "name": "Гамаши"},
                ]
            }
        }
    ]

    result = build_wb_public_snapshot(pages, seller_id=739228)

    assert result.products == 1
    assert result.items[0].nm_id == 1
