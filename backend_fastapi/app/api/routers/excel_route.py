"""Excel export and import routes.

POST /api/v1/excel/export/inventory   — streams an .xlsx of current inventory
POST /api/v1/excel/import/inventory   — ingests an .xlsx and bulk-upserts products
"""
from __future__ import annotations

import io
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_session
from app.shared.schemas import CurrentUser

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/excel", tags=["excel"])

# ─── Export ────────────────────────────────────────────────────────────────────

@router.get("/export/inventory")
async def export_inventory(
    _auth: CurrentUser = Depends(require_permission("inventory.read")),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    """Stream an .xlsx file containing the current in-stock inventory."""
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="openpyxl not installed; Excel export unavailable.",
        )

    rows = await session.execute(
        text(
            """
            SELECT name, manufacturer_barcode, internal_unique_barcode,
                   vendor_name, expiry_date, manufacture_date, price, status,
                   category, lot_number, ndc_code
            FROM products
            WHERE is_deleted = 0 AND status = 'In Stock'
            ORDER BY name
            """
        )
    )
    data = rows.mappings().all()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Inventory"

    # Header styling
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(fill_type="solid", fgColor="1a1a2e")
    headers = [
        "Drug Name", "Mfg Barcode", "Internal Barcode", "Vendor",
        "Expiry Date", "Mfg Date", "Price ($)", "Status",
        "Category", "Lot Number", "NDC Code",
    ]
    for col_idx, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    # Data rows
    for row_idx, record in enumerate(data, 2):
        ws.append([
            record["name"],
            record["manufacturer_barcode"],
            record["internal_unique_barcode"],
            record["vendor_name"],
            record["expiry_date"],
            record["manufacture_date"],
            float(record["price"]),
            record["status"],
            record["category"],
            record.get("lot_number") or "",
            record.get("ndc_code") or "",
        ])

    # Auto-size columns
    for col in ws.columns:
        max_len = max((len(str(cell.value or "")) for cell in col), default=0)
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 40)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = f"inventory_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ─── Import ────────────────────────────────────────────────────────────────────

REQUIRED_COLUMNS = {"name", "price", "manufacturer_barcode", "vendor_name"}
OPTIONAL_COLUMNS = {
    "expiry_date", "manufacture_date", "category",
    "ndc_code", "lot_number", "status",
}

@router.post("/import/inventory", status_code=status.HTTP_200_OK)
async def import_inventory(
    file: UploadFile = File(...),
    _auth: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Ingest an Excel file and bulk-upsert products.

    Required columns: name, price, manufacturer_barcode, vendor_name.
    Returns a summary of inserted/updated/skipped rows.
    """
    if not file.filename or not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(
            status_code=400, detail="Invalid file type. Upload an .xlsx file."
        )

    try:
        import openpyxl
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="openpyxl not installed; Excel import unavailable.",
        )

    contents = await file.read()
    try:
        wb = openpyxl.load_workbook(io.BytesIO(contents), read_only=True, data_only=True)
        ws = wb.active
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Cannot parse Excel file: {exc}")

    # Extract headers from row 1
    header_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), None)
    if not header_row:
        raise HTTPException(status_code=400, detail="Empty spreadsheet.")

    # Normalize headers: strip whitespace, lower-case
    headers = [str(h).strip().lower().replace(" ", "_") if h else "" for h in header_row]

    # Validate required columns
    header_set = set(headers)
    missing = REQUIRED_COLUMNS - header_set
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Missing required columns: {sorted(missing)}"
        )

    inserted = 0
    skipped = 0
    errors: list[str] = []

    async with session.begin():
        for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            record: dict[str, Any] = {
                headers[i]: row[i] for i in range(min(len(headers), len(row)))
            }

            # Validate required fields
            name = str(record.get("name") or "").strip()
            vendor = str(record.get("vendor_name") or "N/A").strip()
            mfg_barcode = str(record.get("manufacturer_barcode") or "").strip()

            try:
                price = float(record.get("price") or 0)
            except (TypeError, ValueError):
                errors.append(f"Row {row_idx}: invalid price value.")
                skipped += 1
                continue

            if not name:
                skipped += 1
                continue

            # Generate a unique internal barcode
            import uuid
            prefix = (vendor[:3] if vendor and vendor != "N/A" else "GEN").upper()
            internal_barcode = f"{prefix}-{str(uuid.uuid4().hex[:6]).upper()}"

            await session.execute(
                text(
                    """
                    INSERT INTO products
                        (name, price, manufacturer_barcode, internal_unique_barcode,
                         vendor_name, expiry_date, manufacture_date, category,
                         ndc_code, lot_number, status)
                    VALUES
                        (:name, :price, :mfg_barcode, :internal_barcode,
                         :vendor, :expiry, :mfg_date, :category,
                         :ndc_code, :lot_number, 'In Stock')
                    """
                ),
                {
                    "name": name,
                    "price": price,
                    "mfg_barcode": mfg_barcode,
                    "internal_barcode": internal_barcode,
                    "vendor": vendor,
                    "expiry": str(record.get("expiry_date") or ""),
                    "mfg_date": str(record.get("manufacture_date") or ""),
                    "category": str(record.get("category") or "Uncategorized"),
                    "ndc_code": record.get("ndc_code"),
                    "lot_number": record.get("lot_number"),
                },
            )
            inserted += 1

    return {
        "inserted": inserted,
        "skipped": skipped,
        "errors": errors,
        "message": f"Import complete: {inserted} inserted, {skipped} skipped.",
    }
