"""Excel export and import routes.

POST /api/v1/excel/export/inventory   — streams an .xlsx of current inventory
POST /api/v1/excel/import/inventory   — ingests an .xlsx and bulk-upserts products
POST /api/v1/excel/import/analyze     — analyzes headers, returns mapping suggestions
POST /api/v1/excel/import/preview     — previews first N rows with mapping applied
POST /api/v1/excel/import/commit      — commits the import with user-defined mapping
"""
from __future__ import annotations

import csv
import io
import logging
import uuid
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

# ─── Column Mapping Helpers ────────────────────────────────────────────────────

DB_FIELDS = {
    "name": {"label": "Drug Name", "required": True, "default": None},
    "price": {"label": "Price", "required": True, "default": None},
    "manufacturer_barcode": {"label": "Mfg Barcode", "required": True, "default": None},
    "vendor_name": {"label": "Vendor", "required": True, "default": None},
    "expiry_date": {"label": "Expiry Date", "required": False, "default": ""},
    "manufacture_date": {"label": "Mfg Date", "required": False, "default": ""},
    "category": {"label": "Category", "required": False, "default": "Uncategorized"},
    "ndc_code": {"label": "NDC Code", "required": False, "default": None},
    "lot_number": {"label": "Lot Number", "required": False, "default": None},
    "status": {"label": "Status", "required": False, "default": "In Stock"},
    "ndc_code": {"label": "NDC Code", "required": False, "default": None},
    "lot_number": {"label": "Lot Number", "required": False, "default": None},
    "dealer_schedule": {"label": "DEA Schedule", "required": False, "default": "OTC"},
    "wholesale_price": {"label": "Wholesale Price", "required": False, "default": 0.0},
    "reorder_threshold": {"label": "Reorder Threshold", "required": False, "default": 0},
    "form": {"label": "Form", "required": False, "default": None},
    "strength": {"label": "Strength", "required": False, "default": None},
    "manufacturer_name": {"label": "Manufacturer", "required": False, "default": None},
    "therapeutic_class": {"label": "Therapeutic Class", "required": False, "default": None},
    "is_generic": {"label": "Is Generic", "required": False, "default": 0},
    "is_controlled": {"label": "Is Controlled", "required": False, "default": 0},
    "maintenance_medication": {"label": "Maintenance Med", "required": False, "default": 0},
    "drug_cost": {"label": "Drug Cost", "required": False, "default": None},
    "default_sig_code": {"label": "Default SIG Code", "required": False, "default": None},
    "default_qty": {"label": "Default Qty", "required": False, "default": None},
    "default_days_supply": {"label": "Default Days Supply", "required": False, "default": None},
    "lot_number": {"label": "Lot Number", "required": False, "default": None},
    "package_size": {"label": "Package Size", "required": False, "default": None},
    "unit_of_measure": {"label": "Unit of Measure", "required": False, "default": None},
    "image_url": {"label": "Image URL", "required": False, "default": None},
}

HEADER_ALIASES = {
    "name": ["name", "drug name", "product name", "medicine", "drug"],
    "price": ["price", "cost", "unit price", "selling price", "retail price"],
    "manufacturer_barcode": ["manufacturer_barcode", "mfg barcode", "mfg_barcode", "barcode", "upc", "gtin", "ean"],
    "vendor_name": ["vendor_name", "vendor", "supplier", "supplier name", "manufacturer"],
    "expiry_date": ["expiry_date", "expiry", "expiration", "exp date", "expiration"],
    "manufacture_date": ["manufacture_date", "mfg_date", "mfg date", "manufacture date", "mfg"],
    "category": ["category", "class", "drug class", "therapeutic class"],
    "ndc_code": ["ndc_code", "ndc", "ndc number", "national drug code"],
    "lot_number": ["lot_number", "lot", "lot no", "lot #"],
    "status": ["status", "state", "inventory status"],
    "category": ["category", "class", "drug class", "therapeutic class"],
    "lot_number": ["lot_number", "lot", "lot no", "lot #"],
    "dealer_schedule": ["dea_schedule", "dea", "schedule"],
    "wholesale_price": ["wholesale_price", "wholesale", "cost", "unit cost", "acquisition cost"],
    "reorder_threshold": ["reorder_threshold", "reorder", "min stock", "min qty", "threshold"],
    "form": ["form", "dosage form", "dosage_form"],
    "strength": ["strength", "str", "potency"],
    "manufacturer_name": ["manufacturer_name", "manufacturer", "mfr", "brand"],
    "therapeutic_class": ["therapeutic_class", "therapeutic class", "class"],
    "is_generic": ["is_generic", "generic", "is generic"],
    "is_controlled": ["is_controlled", "controlled", "controlled substance"],
    "maintenance_medication": ["maintenance_medication", "maintenance", "maintenance med"],
    "drug_cost": ["drug_cost", "cost", "acquisition cost"],
    "default_sig_code": ["default_sig_code", "default sig", "sig code"],
    "default_qty": ["default_qty", "default qty", "default quantity"],
    "default_days_supply": ["default_days_supply", "days supply", "default days"],
    "lot_number": ["lot_number", "lot", "lot no", "lot #"],
    "package_size": ["package_size", "pkg size", "pack size", "size"],
    "unit_of_measure": ["unit_of_measure", "uom", "unit", "unit of measure"],
    "image_url": ["image_url", "image", "photo", "picture"],
}

REQUIRED_DB_FIELDS = {"name", "price", "manufacturer_barcode", "vendor_name"}


def normalize_header(h: str) -> str:
    return h.strip().lower().replace(" ", "_").replace("-", "_")


def auto_map_headers(excel_headers: list[str]) -> tuple[dict[str, int], list[tuple[int, str]]]:
    """Match excel headers to DB fields using aliases. Returns (mapping, unmatched)."""
    mapping: dict[str, int] = {}
    unmatched: list[tuple[int, str]] = []

    normalized_headers = [normalize_header(h) for h in excel_headers]

    for db_field, aliases in HEADER_ALIASES.items():
        for idx, nh in enumerate(normalized_headers):
            if nh in aliases or any(alias in nh for alias in aliases):
                mapping[db_field] = idx
                break

    for idx, nh in enumerate(normalized_headers):
        matched = any(nh in aliases for aliases in HEADER_ALIASES.values())
        if not matched:
            unmatched.append((idx, nh))

    return mapping, unmatched


# ─── Smart Import Endpoints ──────────────────────────────────────────────────

@router.post("/import/analyze", status_code=status.HTTP_200_OK)
async def analyze_import(
    file: UploadFile = File(...),
    _auth: CurrentUser = Depends(require_permission("inventory.read")),
) -> dict[str, Any]:
    """Read Excel/CSV headers and return auto-mapping suggestions."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided.")

    contents = await file.read()
    is_csv = file.filename.lower().endswith(".csv")

    try:
        if file.filename.lower().endswith(".csv"):
            text_content = contents.decode("utf-8-sig")
            import csv as csvmod
            reader = csvmod.reader(io.StringIO(text_content))
            header_row = next(reader, None)
            if not header_row:
                raise HTTPException(status_code=400, detail="Empty CSV file.")
            headers = [str(h).strip() for h in header_row]
            row_count = sum(1 for _ in reader)  # count remaining rows
        else:
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(contents), read_only=True, data_only=True)
            ws = wb.active
            header_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), None)
            if not header_row:
                raise HTTPException(status_code=400, detail="Empty spreadsheet.")
            headers = [str(h).strip() if h else "" for h in header_row]
            row_count = ws.max_row - 1 if ws.max_row > 1 else 0
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Cannot parse file: {exc}")

    headers = [str(h).strip() if h else "" for h in header_row]
    normalized = [normalize_header(h) for h in headers]

    mapping, unmatched = auto_map_headers(headers)
    db_fields = [
        {"key": k, "label": v["label"], "required": v["required"], "default": v["default"]}
        for k, v in DB_FIELDS.items()
    ]

    return {
        "headers": headers,
        "normalized_headers": normalized,
        "row_count": row_count,
        "mapping": mapping,
        "unmatched": unmatched,
        "db_fields": db_fields,
    }


@router.post("/import/preview", status_code=status.HTTP_200_OK)
async def preview_import(
    file: UploadFile = File(...),
    mapping: dict[str, int] = {},
    defaults: dict[str, str] = {},
    limit: int = 20,
    _auth: CurrentUser = Depends(require_permission("inventory.read")),
) -> dict[str, Any]:
    """Preview first N rows with the provided column mapping applied."""
    contents = await file.read()
    is_csv = file.filename.lower().endswith(".csv")

    if is_csv:
        text_content = contents.decode("utf-8-sig")
        import csv as csvmod
        reader = csvmod.DictReader(io.StringIO(text_content))
        rows = list(reader)
    else:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(contents), read_only=True, data_only=True)
        ws = wb.active
        header_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), None)
        if not header_row:
            raise HTTPException(status_code=400, detail="Empty spreadsheet.")
        headers = [str(h).strip().lower().replace(" ", "_") if h else "" for h in header_row]
        rows = []
        for row in ws.iter_rows(min_row=2, max_row=1 + limit, values_only=True):
            record = {headers[i]: row[i] for i in range(min(len(headers), len(row)))}
            rows.append(record)

    preview_rows = []
    for idx, record in enumerate(rows[:limit]):
        preview_row: dict[str, Any] = {"row_index": idx + 2}
        for db_field, col_idx in mapping.items():
            if col_idx < len(headers):
                val = record.get(headers[col_idx], "")
            else:
                val = defaults.get(db_field, DB_FIELDS[db_field].get("default", ""))
            preview_row[db_field] = val

        # Validate required fields
        missing_required = []
        for field in REQUIRED_DB_FIELDS:
            if not preview_row.get(field):
                missing_required.append(field)
        preview_row["_missing_required"] = missing_required
        preview_rows.append(preview_row)

    return {"rows": preview_rows, "total_rows": len(rows)}


@router.post("/import/commit", status_code=status.HTTP_200_OK)
async def commit_import(
    file: UploadFile = File(...),
    mapping: dict[str, int] = {},
    defaults: dict[str, str] = {},
    generate_labels: bool = False,
    _auth: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Commit the import with user-defined mapping.

    When ``generate_labels`` is true, every successfully imported product gets a
    per-product label row (product_labels) copied from the default label
    template — neatly queueing the imported batch for label printing.
    """
    contents = await file.read()
    is_csv = file.filename.lower().endswith(".csv")

    if file.filename.lower().endswith(".csv"):
        text_content = contents.decode("utf-8-sig")
        import csv as csvmod
        reader = csvmod.DictReader(io.StringIO(text_content))
        rows = list(reader)
    else:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(contents), read_only=True, data_only=True)
        ws = wb.active
        header_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), None)
        if not header_row:
            raise HTTPException(status_code=400, detail="Empty spreadsheet.")
        headers = [str(h).strip().lower().replace(" ", "_") if h else "" for h in header_row]
        rows = []
        for row in ws.iter_rows(min_row=2, values_only=True):
            record = {headers[i]: row[i] for i in range(min(len(headers), len(row)))}
            rows.append(record)

    inserted = 0
    skipped = 0
    errors: list[str] = []

    async with session.begin():
        for row_idx, record in enumerate(rows, start=2):
            preview_row: dict[str, Any] = {}
            for db_field, col_idx in mapping.items():
                if col_idx < len(headers):
                    val = record.get(headers[col_idx], "")
                else:
                    val = defaults.get(db_field, DB_FIELDS[db_field].get("default", ""))
                preview_row[db_field] = val

            # Validate required fields
            missing_required = []
            for field in REQUIRED_DB_FIELDS:
                if not preview_row.get(field):
                    missing_required.append(field)
            if missing_required:
                errors.append(f"Row {row_idx}: missing required fields: {', '.join(missing_required)}")
                skipped += 1
                continue

            name = str(preview_row.get("name") or "").strip()
            vendor = str(preview_row.get("vendor_name") or "N/A").strip()
            mfg_barcode = str(preview_row.get("manufacturer_barcode") or "").strip()

            try:
                price = float(preview_row.get("price") or 0)
            except (TypeError, ValueError):
                errors.append(f"Row {row_idx}: invalid price value.")
                skipped += 1
                continue

            if not name:
                skipped += 1
                continue

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
                    "expiry": str(preview_row.get("expiry_date") or ""),
                    "mfg_date": str(preview_row.get("manufacture_date") or ""),
                    "category": str(preview_row.get("category") or "Uncategorized"),
                    "ndc_code": preview_row.get("ndc_code"),
                    "lot_number": preview_row.get("lot_number"),
                },
            )
            inserted += 1

            # Queue a label for this product from the default template
            # ("Generate Labels on Import" — Spec: Objective 2).
            if generate_labels and default_tpl is not None:
                product_id_row = (
                    await session.execute(
                        text("SELECT id FROM products WHERE internal_unique_barcode = :bc"),
                        {"bc": internal_barcode},
                    )
                ).first()
                if product_id_row:
                    await session.execute(
                        text(
                            "INSERT OR IGNORE INTO product_labels "
                            "(product_id, canvas_width, canvas_height, elements, updated_at) "
                            "VALUES (:pid, :w, :h, :elements, :updated_at)"
                        ),
                        {
                            "pid": product_id_row[0],
                            "w": default_tpl["canvas_width"],
                            "h": default_tpl["canvas_height"],
                            "elements": default_tpl["elements"],
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                        },
                    )
                    labels_queued += 1

    return {
        "inserted": inserted,
        "skipped": skipped,
        "errors": errors,
        "message": f"Import complete: {inserted} inserted, {skipped} skipped."
        + (f" {labels_queued} label(s) queued for printing." if generate_labels else ""),
    }

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


# ─── CSV Import ──────────────────────────────────────────────────────────────

@router.post("/import/csv", status_code=status.HTTP_200_OK)
async def import_csv(
    file: UploadFile = File(...),
    _auth: CurrentUser = Depends(require_permission("inventory.write")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Ingest a CSV file and bulk-upsert products.

    Required columns: name, price, manufacturer_barcode, vendor_name.
    """
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=400, detail="Invalid file type. Upload a .csv file."
        )

    import csv as csvmod

    contents = await file.read()
    try:
        text_data = contents.decode("utf-8-sig")
    except UnicodeDecodeError:
        text_data = contents.decode("latin-1")

    reader = csvmod.DictReader(io.StringIO(text_data))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV has no headers.")

    headers = [h.strip().lower().replace(" ", "_") for h in reader.fieldnames]
    reader.fieldnames = headers

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
        for row_idx, record in enumerate(reader, start=2):
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
        "message": f"CSV import complete: {inserted} inserted, {skipped} skipped.",
    }
