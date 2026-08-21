"""License proxy: forwards license requests to the isolated Flask license service
(`backend/app.py` on LICENSE_GATE_URL) and returns 502 when it is unreachable.
"""
from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_session
from app.core.repositories import LicenseRepository
from app.shared.config import settings
from app.shared.exceptions import LicenseGatewayError
from app.shared.schemas import CreemCheckoutRequest, CreemCheckoutResponse, CurrentUser, LicenseValidationResult

router = APIRouter(prefix="/api/v1/license", tags=["license"])

_GATEWAY_TIMEOUT = 5.0


@router.post("/validate", response_model=LicenseValidationResult)
async def validate_license(
    request: Request,
    _user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> LicenseValidationResult | JSONResponse:
    body_json = await request.json()
    license_key = body_json.get("license_key")
    hardware_id = body_json.get("hardware_id")
    
    if license_key and hardware_id:
        repo = LicenseRepository(session)
        async with session.begin():
            # Check local license DB first (Creem fulfillment)
            lic = await repo.get_by_key(license_key)
            if lic:
                # Bind hardware id on first use
                if not lic.hardware_id:
                    lic = await repo.bind_hardware(license_key, hardware_id)
                elif lic.hardware_id != hardware_id:
                    raise HTTPException(status_code=403, detail="Hardware ID mismatch")
                
                return LicenseValidationResult.model_validate(lic)

    # Fallback to isolated Flask service
    body = await request.body()
    return await _proxy("POST", "/api/validate", body, request)


@router.post("/checkout", response_model=CreemCheckoutResponse, status_code=status.HTTP_201_CREATED)
async def create_checkout_session(
    payload: CreemCheckoutRequest,
    _user: CurrentUser = Depends(get_current_user),
) -> CreemCheckoutResponse:
    """Create a Creem hosted checkout session."""
    api_key = settings.creem_api_key.get_secret_value()
    if not api_key:
        raise HTTPException(status_code=503, detail="Creem MoR integration is not configured")
        
    product_id = payload.product_id or settings.creem_product_id
    if not product_id:
        raise HTTPException(status_code=500, detail="Creem product ID is missing")

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                "https://api.creem.io/v1/checkouts",
                headers={
                    "X-Api-Key": api_key,
                    "Content-Type": "application/json"
                },
                json={
                    "product_id": product_id,
                    "success_url": payload.success_url,
                    "cancel_url": payload.cancel_url,
                    "metadata": payload.metadata
                }
            )
            resp.raise_for_status()
            data = resp.json()
            return CreemCheckoutResponse(
                checkout_id=data.get("id", ""),
                checkout_url=data.get("url", "")
            )
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"Failed to create checkout session: {str(exc)}")


@router.post("/admin/manage")
async def admin_manage(
    request: Request,
    _user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    body = await request.body()
    return await _proxy("POST", "/api/admin/manage", body, request)


@router.get("/status")
async def license_status(
    _user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    try:
        async with httpx.AsyncClient(timeout=_GATEWAY_TIMEOUT) as client:
            resp = await client.get(f"{settings.license_gate_url}/api/admin/manage")
            return JSONResponse(
                status_code=resp.status_code,
                content={"status": "reachable", "http_status": resp.status_code},
            )
    except (httpx.ConnectError, httpx.ReadTimeout):
        raise LicenseGatewayError(
            f"License service unreachable at {settings.license_gate_url}",
        )


async def _proxy(method: str, path: str, body: bytes, request: Request) -> JSONResponse:
    url = f"{settings.license_gate_url}{path}"
    headers: dict[str, str] = {}
    admin_secret = request.headers.get("x-admin-secret")
    if admin_secret:
        headers["X-Admin-Secret"] = admin_secret
    try:
        async with httpx.AsyncClient(timeout=_GATEWAY_TIMEOUT) as client:
            resp = await client.request(method, url, content=body, headers=headers)
    except (httpx.ConnectError, httpx.ReadTimeout) as exc:
        raise LicenseGatewayError(
            f"License service unreachable at {settings.license_gate_url}",
            details={"path": path, "error": str(exc)},
        )
    content: Any = resp.content
    try:
        content = resp.json()
    except ValueError:
        pass
    return JSONResponse(status_code=resp.status_code, content=content)
