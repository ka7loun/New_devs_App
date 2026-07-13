from fastapi import APIRouter, Depends, HTTPException, Query, status
from typing import Dict, Any
from app.services.cache import get_revenue_summary
from app.core.auth import authenticate_request as get_current_user

router = APIRouter()

@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    month: int = Query(3, ge=1, le=12),
    year: int = Query(2024, ge=2000, le=2100),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="A tenant context is required",
        )

    revenue_data = await get_revenue_summary(property_id, tenant_id, month, year)
    
    return {
        "property_id": revenue_data['property_id'],
        # A fixed-point string prevents a precise Decimal from becoming a
        # binary floating-point value while crossing the JSON boundary.
        "total_revenue": revenue_data['total'],
        "currency": revenue_data['currency'],
        "reservations_count": revenue_data['count'],
        "month": month,
        "year": year,
    }
