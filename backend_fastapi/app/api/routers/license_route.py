"""License proxy: forwards license requests to the isolated Flask license service
(`backend/app.py` on LICENSE_GATE_URL) and returns 502 when it is unreachable.
"""
from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse

from app.api.deps import get_current_user
from app.shared.config import settings
from app.shared.exceptions import LicenseGatewayError
from app.shared.schemas import CurrentUser

router = APIRouter(prefix="/api/v1/license", tags=["license"])

_GATEWAY_TIMEOUT = 5.0


@router.post("/validate")
async def validate_license(
    request: Request,
    _user: CurrentUser = Depends(get_current_user),
) -> JSONResponse:
    body = await request.body()
    return await _proxy("POST", "/api/validate", body, request)


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
