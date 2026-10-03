#!/usr/bin/env python3
"""Load the fake demo dataset (seed_demo.json) into a FRESH Pharmacy Suite database.

Purpose: screenshots and sales demos. ALL data is fake and DEMO-marked; the
loader never touches an existing user database unless pointed at it explicitly
via --db.

Usage (from repo root, backend venv):
    backend_fastapi/.venv/Scripts/python release/demo/load_demo.py
    backend_fastapi/.venv/Scripts/python release/demo/load_demo.py --db C:/path/demo.db
    backend_fastapi/.venv/Scripts/python release/demo/load_demo.py --clean   # remove DEMO rows only

The loader mirrors backend_fastapi/app/main.py lifespan exactly: init_engine ->
create_schema -> seed_* defaults -> demo rows -> setup_complete=true (so the
first-run wizard does not block screenshots). No migrations are run manually;
create_schema handles a fresh DB.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend_fastapi"
SEED_FILE = Path(__file__).resolve().parent / "seed_demo.json"
DEFAULT_DB = Path(__file__).resolve().parent / "pharmacy-demo.db"

DEMO_MARKER_PREFIX = "DEMO-"


def _out(s: str) -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    print(s, flush=True)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db", type=Path, default=DEFAULT_DB, help="Target SQLite file (default: release/demo/pharmacy-demo.db)")
    p.add_argument("--admin-password", default="demo-admin-2026", help="Password for the demo admin user (default: demo-admin-2026)")
    p.add_argument("--clean", action="store_true", help="Delete only DEMO-marked rows before loading (idempotent re-load)")
    p.add_argument("--seed", type=Path, default=SEED_FILE, help="Path to seed_demo.json")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    db_path = args.db if args.db.is_absolute() else (REPO_ROOT / args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists() and not args.clean:
        sys.exit(f"Refusing to overwrite existing DB {db_path}. Pass --clean to wipe DEMO rows and reload, or delete the file.")

    # 1) Point the app at the target DB BEFORE any app import (pydantic Settings
    #    reads PHARMACY_DB_URL at import time).
    url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    os.environ["PHARMACY_DB_URL"] = url

    sys.path.insert(0, str(BACKEND_DIR))

    # App imports happen strictly after the env var is set.
    from app.core.database import (  # noqa: E402
        create_schema, get_session, init_engine,
    )
    from app.core.models import (  # noqa: E402
        Patient, Product, Receipt, ReceiptItem, Role, SystemSetting, Supplier, User,
    )
    from app.core.repositories import UserRepository  # noqa: E402
    from app.services.seed_service import (  # noqa: E402
        seed_clinical_defaults, seed_default_locked_features, seed_default_settings,
        seed_drug_dictionary, seed_product_templates, seed_session_settings,
    )
    from app.shared.security import hash_password  # noqa: E402
    from sqlalchemy import delete, func, select  # noqa: E402
    from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

    import asyncio  # noqa: E402

    seed = json.loads(args.seed.read_text(encoding="utf-8"))

    async def run(session: AsyncSession) -> dict:
        # 2) Schema + the app's own default seeds (roles, dictionaries, settings).
        # (Engine already initialized in runner() before get_session().)
        await create_schema()
        await seed_clinical_defaults(session)
        await seed_default_locked_features(session)
        await seed_drug_dictionary(session)
        await seed_session_settings(session)
        await seed_product_templates(session)
        await seed_default_settings(session)

        if args.clean:
            # Delete ONLY rows carrying DEMO markers (idempotent reload).
            for model, col in (
                (ReceiptItem, ReceiptItem.internal_barcode),
                (Product, Product.internal_unique_barcode),
                (Supplier, Supplier.tax_id),
            ):
                await session.execute(delete(model).where(col.like(f"{DEMO_MARKER_PREFIX}%")))
            demo_patients = (await session.execute(select(Patient).where(Patient.name.like("%(demo)%")))).scalars().all()
            for pat in demo_patients:
                await session.delete(pat)
            demo_receipts = (await session.execute(select(Receipt).where(Receipt.created_by == "demo"))).scalars().all()
            for rc in demo_receipts:
                await session.delete(rc)
            demo_users = (await session.execute(select(User).where(User.username == "demo"))).scalars().all()
            for usr in demo_users:
                await session.delete(usr)
            await session.flush()

        # 3) Admin role + demo admin user (mirrors setup_route.py first-run flow).
        role_id_row = await session.scalar(select(Role.id).limit(1))
        if role_id_row is None:
            from app.services.seed_service import seed_admin_role
            await seed_admin_role(session)
            role_id_row = await session.scalar(select(Role.id).limit(1))
        admin_repo = UserRepository(session)
        await admin_repo.create(
            username="demo",
            display_name="Demo Owner",
            password_hash=hash_password(args.admin_password),
            role_id=role_id_row,
        )

        # 4) Pharmacy identity so receipts/headers look right.
        for key, val in {"pharmacy_name": "Demo Pharmacy (Apex Software)", "setup_complete": "true"}.items():
            existing = await session.get(SystemSetting, key)
            if existing is None:
                session.add(SystemSetting(key=key, value=val.encode("utf-8")))
            else:
                existing.value = val.encode("utf-8")

        # 5) Suppliers (DEMO tax-id marker).
        supplier_ids: list[int] = []
        for sup in seed["suppliers"]:
            obj = Supplier(
                name=sup["name"], contact_name=sup.get("contact_name"), contact_email=sup.get("contact_email"),
                contact_phone=sup.get("contact_phone"), address=sup.get("address"), tax_id=sup["tax_id"],
                preferred=sup.get("preferred", 0), min_stock_level=sup.get("min_stock_level"),
                lead_time_days=sup.get("lead_time_days"),
                created_at=datetime.now().isoformat(timespec="seconds"),
            )
            session.add(obj)
            await session.flush()
            supplier_ids.append(obj.id)

        # 6) Products (DEMO internal barcodes; expiry = today + offset).
        products: list[Product] = []
        for idx, prod in enumerate(seed["products"], start=1):
            expiry = (date.today() + timedelta(days=prod["expiry_offset_days"])).isoformat()
            mfg = (date.today() - timedelta(days=365)).isoformat()
            obj = Product(
                name=prod["name"], price=Decimal(prod["price"]),
                manufacturer_barcode=prod["manufacturer_barcode"],
                internal_unique_barcode=f"{DEMO_MARKER_PREFIX}P{idx:04d}",
                status="In Stock" if prod["on_hand"] > 10 else "Low Stock",
                expiry_date=expiry, manufacture_date=mfg,
                vendor_name=seed["suppliers"][idx % len(seed["suppliers"])]["name"],
                wholesale_price=Decimal(prod["wholesale_price"]), category=prod["category"],
                lot_number=f"{DEMO_MARKER_PREFIX}L{idx:04d}", package_size="1",
                unit_of_measure="unit", form=prod.get("form") or None,
                strength=prod.get("strength") or None,
                manufacturer_name=prod.get("manufacturer_name") or None,
                is_generic=prod.get("is_generic", 0), drug_cost=Decimal(prod["wholesale_price"]),
            )
            session.add(obj)
            products.append(obj)
        await session.flush()

        # 7) Patients.
        patient_ids: list[int] = []
        for pat in seed["patients"]:
            obj = Patient(
                name=pat["name"], dob=pat["dob"], sex=pat["sex"], address=pat["address"],
                contact_phone=pat["contact_phone"], email=pat["email"],
                insurance_provider=pat.get("insurance_provider", ""),
                policy_number=pat.get("policy_number", ""), group_number=pat.get("group_number", ""),
                patient_allergies=pat.get("patient_allergies", ""),
                created_at=datetime.now().isoformat(timespec="seconds"),
            )
            session.add(obj)
            patient_ids.append(obj.id)
        await session.flush()

        # 8) Receipts + items (receipt id is back-filled after flush).
        now = datetime.now()
        for ridx, rec in enumerate(seed["receipts"], start=1):
            items_spec = rec["items"]
            total = sum(Decimal(products[i].price) * qty for i, qty in ((it["p"], it["qty"]) for it in items_spec))
            ts = (now - timedelta(days=rec["days_ago"], hours=9 + ridx)).isoformat(timespec="seconds")
            rc = Receipt(
                timestamp=ts, total_amount=total, payment_method=rec["payment_method"],
                patient_id=None if rec["patient_index"] is None else patient_ids[rec["patient_index"]],
                server_created_at=ts, created_by="demo", cashier_attribution="Demo Owner",
                client_tx_id=f"{DEMO_MARKER_PREFIX}TX{ridx:04d}", sale_type="OTC",
            )
            session.add(rc)
            await session.flush()
            for it in items_spec:
                prod = products[it["p"]]
                session.add(ReceiptItem(
                    receipt_id=rc.id, product_name=prod.name, quantity=it["qty"],
                    price_at_time=prod.price, internal_barcode=prod.internal_unique_barcode,
                    vendor=prod.vendor_name, expiry_date=prod.expiry_date,
                ))

        counts = {}
        for label, model in (("products", Product), ("patients", Patient), ("receipts", Receipt), ("suppliers", Supplier)):
            counts[label] = await session.scalar(select(func.count()).select_from(model))
        return counts

    async def runner() -> dict:
        # init_engine MUST precede get_session(): otherwise get_session falls back
        # to the default app-data URL and the session binds to the wrong database
        # (same ordering as main.py lifespan: init_engine -> create_schema -> routes).
        init_engine(url)
        # Use the app's own session dependency (no private sessionmaker access).
        # NOTE: the app's seed helpers commit internally, so we do NOT wrap in
        # session.begin(); we commit once at the end (same style as setup_route.py).
        agen = get_session()
        session = await agen.__anext__()
        try:
            counts = await run(session)
            await session.commit()
            return counts
        except Exception:
            await session.rollback()
            raise
        finally:
            await agen.aclose()

    counts = asyncio.run(runner())
    _out(f"Demo DB ready: {db_path}")
    _out(f"Counts: {counts}")
    _out(f"Demo login -> username: demo   password: {args.admin_password}")
    _out("All rows are DEMO-marked / (demo)-suffixed. Real data: none.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
