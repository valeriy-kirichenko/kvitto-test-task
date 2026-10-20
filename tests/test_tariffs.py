import httpx

EXPECTED_PRICES = {"basic": 990_000, "standard": 1_990_000, "premium": 2_990_000}


async def test_get_tariffs_returns_list_of_objects(client: httpx.AsyncClient) -> None:
    """``GET /tariffs``: 200 и список объектов с полями ``id``, ``title``, ``price``."""
    response = await client.get("/tariffs")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    for item in body:
        assert set(item) == {"id", "title", "price"}, item


async def test_get_tariffs_contains_all_tariffs_with_expected_prices(
    client: httpx.AsyncClient,
) -> None:
    """Все три тарифа из ТЗ с ценами в копейках (целые числа)."""
    response = await client.get("/tariffs")
    assert response.status_code == 200
    prices = {item["title"]: item["price"] for item in response.json()}
    assert prices == EXPECTED_PRICES
    for price in prices.values():
        assert isinstance(price, int), f"Цена должна быть целым числом: {price}"
