"""Uniform error contract: every error response is ``{"error": {"code", "message", "details"}}``."""
from __future__ import annotations

from typing import Any, Optional


class AppException(Exception):
    """Base class for all application errors.

    Serialized by the global FastAPI exception handler into the mandatory
    uniform JSON error contract.
    """

    def __init__(
        self,
        message: str,
        status_code: int = 500,
        error_code: str = "app_error",
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.details: dict[str, Any] = details or {}
        super().__init__(message)


class ValidationError(AppException):
    def __init__(self, message: str, details: Optional[dict[str, Any]] = None) -> None:
        super().__init__(message, status_code=400, error_code="validation_error", details=details)


class NotFoundError(AppException):
    def __init__(self, resource: str, resource_id: Any) -> None:
        super().__init__(
            f"{resource} not found: {resource_id}",
            status_code=404,
            error_code="not_found",
            details={"resource": resource, "id": resource_id},
        )


class InsufficientStockError(AppException):
    def __init__(self, medicine_name: str, available: int, requested: int) -> None:
        super().__init__(
            f"Insufficient stock for {medicine_name}: {requested} requested, {available} available",
            status_code=400,
            error_code="insufficient_stock",
            details={"medicine_name": medicine_name, "requested": requested, "available": available},
        )


class UnauthorizedError(AppException):
    def __init__(self, message: str = "Authentication required") -> None:
        super().__init__(message, status_code=401, error_code="unauthorized")


class ForbiddenError(AppException):
    def __init__(self, message: str = "Insufficient permissions") -> None:
        super().__init__(message, status_code=403, error_code="forbidden")


class ConflictError(AppException):
    def __init__(self, message: str, details: Optional[dict[str, Any]] = None) -> None:
        super().__init__(message, status_code=409, error_code="conflict", details=details)


class StockStateError(AppException):
    """Base class for stock-state violations surfaced as ``410 Gone``.

    A ``410`` (rather than ``400``/``409``) tells the client the request can
    never succeed in its current form and must be **parked** (not retried in a
    tight loop) — the offline queue routes these to the discrepancies panel so
    the sync loop always advances to the next item.
    """

    def __init__(
        self,
        message: str,
        error_code: str = "stock_state",
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, status_code=410, error_code=error_code, details=details)


class OverSellError(StockStateError):
    def __init__(self, medicine_name: str, available: int, requested: int) -> None:
        super().__init__(
            f"Over-sell prevented for {medicine_name}: {requested} requested, {available} available",
            error_code="over_sell",
            details={"medicine_name": medicine_name, "requested": requested, "available": available},
        )


class ExpiredLotError(StockStateError):
    def __init__(self, medicine_name: str, lot_number: str, expiry_date: str) -> None:
        super().__init__(
            f"Expired lot for {medicine_name}: lot {lot_number} expired {expiry_date}",
            error_code="expired_lot",
            details={"medicine_name": medicine_name, "lot_number": lot_number, "expiry_date": expiry_date},
        )


class RecalledLotError(StockStateError):
    def __init__(self, medicine_name: str, lot_number: str) -> None:
        super().__init__(
            f"Recalled lot for {medicine_name}: lot {lot_number} has been recalled",
            error_code="recalled_lot",
            details={"medicine_name": medicine_name, "lot_number": lot_number},
        )


class MissingLotError(StockStateError):
    def __init__(self, medicine_name: str) -> None:
        super().__init__(
            f"No sellable lot for {medicine_name}",
            error_code="missing_lot",
            details={"medicine_name": medicine_name},
        )


class LicenseGatewayError(AppException):
    def __init__(self, message: str, details: Optional[dict[str, Any]] = None) -> None:
        super().__init__(message, status_code=502, error_code="license_unreachable", details=details)
