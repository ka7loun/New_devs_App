import unittest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from app.services import cache
from app.services.reservations import get_month_utc_bounds, round_currency


class FakeRedis:
    def __init__(self):
        self.values = {}

    async def get(self, key):
        return self.values.get(key)

    async def setex(self, key, _ttl, value):
        self.values[key] = value


class RevenueCacheIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def test_same_property_id_is_cached_separately_per_tenant(self):
        fake_redis = FakeRedis()
        calculate = AsyncMock(
            side_effect=[
                {
                    "property_id": "prop-001",
                    "tenant_id": "tenant-a",
                    "total": "2250.00",
                    "currency": "USD",
                    "count": 4,
                },
                {
                    "property_id": "prop-001",
                    "tenant_id": "tenant-b",
                    "total": "0.00",
                    "currency": "USD",
                    "count": 0,
                },
            ]
        )

        with patch.object(cache, "redis_client", fake_redis), patch(
            "app.services.reservations.calculate_total_revenue", calculate
        ):
            sunset = await cache.get_revenue_summary(
                "prop-001", "tenant-a", 3, 2024
            )
            ocean = await cache.get_revenue_summary(
                "prop-001", "tenant-b", 3, 2024
            )
            sunset_cached = await cache.get_revenue_summary(
                "prop-001", "tenant-a", 3, 2024
            )

        self.assertEqual("2250.00", sunset["total"])
        self.assertEqual("0.00", ocean["total"])
        self.assertEqual(sunset, sunset_cached)
        self.assertEqual(2, calculate.await_count)
        self.assertEqual(
            {
                "revenue:tenant-a:prop-001:2024:03",
                "revenue:tenant-b:prop-001:2024:03",
            },
            set(fake_redis.values),
        )


class RevenueDateAndPrecisionTests(unittest.TestCase):
    def test_paris_march_uses_property_local_boundary(self):
        start, end = get_month_utc_bounds(2024, 3, "Europe/Paris")

        self.assertEqual(datetime(2024, 2, 29, 23, tzinfo=timezone.utc), start)
        self.assertEqual(datetime(2024, 3, 31, 22, tzinfo=timezone.utc), end)

    def test_new_york_march_uses_property_local_boundary(self):
        start, end = get_month_utc_bounds(2024, 3, "America/New_York")

        self.assertEqual(datetime(2024, 3, 1, 5, tzinfo=timezone.utc), start)
        self.assertEqual(datetime(2024, 4, 1, 4, tzinfo=timezone.utc), end)

    def test_sub_cent_values_are_summed_before_rounding(self):
        aggregate = sum(
            (Decimal("333.333"), Decimal("333.333"), Decimal("333.334")),
            Decimal("0"),
        )

        self.assertEqual(Decimal("1000.00"), round_currency(aggregate))


if __name__ == "__main__":
    unittest.main()
