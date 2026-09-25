"""Tests for the new `/api/v1/dashboard/analytics` endpoint.

The endpoint returns a static mock payload. The test verifies:
* The request succeeds with a 200 status.
* The response contains the expected keys with the correct types.
* Permission `analytics.read` is enforced via an admin token.
"""

from httpx import AsyncClient

# Reuse the helper functions from other tests for seeding an admin user and
# obtaining an access token.
from .test_auth import _admin_token  # noqa: F401


async def test_dashboard_analytics(client: AsyncClient, session) -> None:
    # Obtain a bearer token with sufficient permissions.
    token = await _admin_token(client, session)

    # Call the analytics endpoint.
    resp = await client.get(
        "/api/v1/dashboard/analytics",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, f"Unexpected status {resp.status_code}: {resp.text}"

    data = resp.json()
    # Validate the top‑level keys.
    assert "total_sales" in data and isinstance(data["total_sales"], (int, float))
    assert "total_customers" in data and isinstance(data["total_customers"], int)
    assert "top_items" in data and isinstance(data["top_items"], list)

    # Validate structure of each top item.
    for item in data["top_items"]:
        assert isinstance(item, dict)
        assert "product_name" in item and isinstance(item["product_name"], str)
        assert "total_quantity" in item and isinstance(item["total_quantity"], int)
        assert "total_revenue" in item and isinstance(item["total_revenue"], (int, float))