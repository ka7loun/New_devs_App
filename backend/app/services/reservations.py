from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Optional, Tuple
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


CURRENCY_QUANTUM = Decimal("0.01")


def round_currency(value: Any) -> Decimal:
    """Round a completed aggregate once, using standard financial rounding."""
    return Decimal(str(value or "0")).quantize(
        CURRENCY_QUANTUM, rounding=ROUND_HALF_UP
    )


def get_month_utc_bounds(
    year: int, month: int, timezone_name: str
) -> Tuple[datetime, datetime]:
    """Return UTC boundaries for a calendar month in a property's timezone."""
    if month < 1 or month > 12:
        raise ValueError("month must be between 1 and 12")

    property_timezone = ZoneInfo(timezone_name)
    start_local = datetime(year, month, 1, tzinfo=property_timezone)
    if month == 12:
        end_local = datetime(year + 1, 1, 1, tzinfo=property_timezone)
    else:
        end_local = datetime(year, month + 1, 1, tzinfo=property_timezone)

    return (
        start_local.astimezone(timezone.utc),
        end_local.astimezone(timezone.utc),
    )


async def _query_monthly_revenue(
    session: AsyncSession,
    property_id: str,
    tenant_id: str,
    month: int,
    year: int,
) -> Dict[str, Any]:
    property_result = await session.execute(
        text(
            """
            SELECT timezone
            FROM properties
            WHERE id = :property_id AND tenant_id = :tenant_id
            """
        ),
        {"property_id": property_id, "tenant_id": tenant_id},
    )
    property_row = property_result.fetchone()

    # Looking up the property with the tenant in the same predicate prevents a
    # caller from using a valid property ID that belongs to another tenant.
    if not property_row:
        return {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "total": "0.00",
            "currency": "USD",
            "count": 0,
            "month": month,
            "year": year,
        }

    start_utc, end_utc = get_month_utc_bounds(year, month, property_row.timezone)
    revenue_result = await session.execute(
        text(
            """
            SELECT
                SUM(total_amount) AS total_revenue,
                COUNT(*) AS reservation_count
            FROM reservations
            WHERE property_id = :property_id
              AND tenant_id = :tenant_id
              AND check_in_date >= :start_utc
              AND check_in_date < :end_utc
            """
        ),
        {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "start_utc": start_utc,
            "end_utc": end_utc,
        },
    )
    row = revenue_result.fetchone()
    total = round_currency(row.total_revenue if row else None)

    return {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "total": format(total, ".2f"),
        "currency": "USD",
        "count": int(row.reservation_count if row else 0),
        "month": month,
        "year": year,
    }


async def calculate_monthly_revenue(
    property_id: str,
    month: int,
    year: int,
    db_session: Optional[AsyncSession] = None,
    tenant_id: Optional[str] = None,
) -> Decimal:
    """Calculate tenant-isolated revenue for a property-local calendar month."""
    if not tenant_id:
        raise ValueError("tenant_id is required for revenue calculations")

    if db_session is not None:
        result = await _query_monthly_revenue(
            db_session, property_id, tenant_id, month, year
        )
    else:
        result = await calculate_total_revenue(property_id, tenant_id, month, year)

    return Decimal(result["total"])


async def calculate_total_revenue(
    property_id: str,
    tenant_id: str,
    month: int = 3,
    year: int = 2024,
) -> Dict[str, Any]:
    """Return the monthly dashboard summary for one tenant and property."""
    from app.core.database_pool import db_pool

    if db_pool.session_factory is None:
        await db_pool.initialize()
    if db_pool.session_factory is None:
        raise RuntimeError("Database pool is not available")

    async with db_pool.get_session() as session:
        return await _query_monthly_revenue(
            session, property_id, tenant_id, month, year
        )
