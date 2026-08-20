"""B8 — direct-await unit tests for the four async services.

Coverage.py (7.15.4) in this env does not trace async coroutine bodies driven
through the AsyncClient/ASGI HTTP path, but DOES trace them under a direct
``await`` inside the test coroutine. These tests therefore exercise the service
methods directly (using the existing in-memory aiosqlite ``session`` fixture) so
their bodies are counted and measured coverage can reach the >=90% gate.
"""
from __future__ import annotations

import os

import pytest
from decimal import Decimal
from sqlalchemy import select, text

import app.services.auth_service as auth_mod
from app.core.models import (
    DrawerMovement,
    InventoryExtended,
    Permission,
    Product,
    Receipt,
    ReceiptItem,
    Refund,
    Role,
    RolePermission,
    Shift,
    SyncInventory,
)
from app.core.repositories import BatchRepository, SyncRepository, UserRepository
from app.services.auth_service import AuthService, _parse_locked_until
from app.services.inventory_service import InventoryService
from app.services.pos_service import PosService
from app.services.sync_service import SyncService
from app.shared import config as config_mod
from app.shared.exceptions import (
    AppException,
    ConflictError,
    ExpiredLotError,
    ForbiddenError,
    MissingLotError,
    NotFoundError,
    OverSellError,
    RecalledLotError,
    UnauthorizedError,
    ValidationError,
)
from app.shared.schemas import (
    BatchUpdate,
    CheckoutLineIn,
    CheckoutRequest,
    CurrentUser,
    DrawerMovementCreate,
    RefundRequest,
    ShiftCloseRequest,
    ShiftOpenRequest,
    SyncPushEntry,
    UserCreate,
)
from app.shared.security import hash_password, set_pin_pepper, PinPepper

class _NoPepper:
    """Stand-in for a pepper resolver whose derive() yields None (no pepper)."""

    def derive(self):
        return None


PERMS = [
    "inventory.read",
    "inventory.write",
    "inventory.reports",
    "pos.checkout",
    "pos.drawer",
    "users.write",
]


@pytest.fixture
async def role_and_perms(session):
    role = Role(name="admin", description="admin", is_system=1)
    session.add(role)
    await session.commit()
    for key in PERMS:
        session.add(Permission(feature_key=key, description=key))
    await session.commit()
    perms = (await session.execute(select(Permission))).scalars().all()
    for p in perms:
        session.add(RolePermission(role_id=role.id, permission_id=p.id, granted=1))
    await session.commit()
    return role


@pytest.fixture
async def admin_user(session, role_and_perms):
    user = await UserRepository(session).create(
        "adminroot", "Admin", hash_password("Password123!@#"), role_and_perms.id
    )
    return user


@pytest.fixture
def pin_pepper():
    os.environ["PHARMACY_PEPPER_KEY"] = "test-pepper-secret-0123456789"
    set_pin_pepper(
        PinPepper(backend="env", env_key="PHARMACY_PEPPER_KEY", path="pepper_test.bin")
    )
    yield
    set_pin_pepper(None)


def _product(session, name="Paracetamol", price=10.0):
    session.add(
        Product(
            name=name,
            price=Decimal(str(price)),
            internal_unique_barcode=f"INT-{name[:3].upper()}",
            vendor_name="Acme",
            expiry_date="2030-01-01",
        )
    )


async def _seed_product(session, name="Paracetamol", price=10.0):
    _product(session, name, price)
    await session.commit()


async def _receive(session, name, qty, lot="L1", expiry="2030-01-01"):
    await InventoryService(session).receive_batch(name, lot, expiry, qty, 1.0, "Acme")
    await session.commit()


# ─────────────────────────── POS service ───────────────────────────


async def test_skew_bad_timestamp(session):
    await _seed_product(session)
    await _receive(session, "Paracetamol", 4)
    payload = CheckoutRequest(
        line_items=[CheckoutLineIn(product_name="Paracetamol", quantity=1)],
        client_timestamp="not-a-real-timestamp",
    )
    user = CurrentUser(id=1, username="adminroot", role="admin", permissions=["pos.checkout"])
    result = await PosService(session).process_checkout(payload, user)
    assert result.receipt_number.startswith("RCP-")


async def test_pos_checkout_success(session):
    await _seed_product(session)
    await _receive(session, "Paracetamol", 4)
    payload = CheckoutRequest(
        line_items=[CheckoutLineIn(product_name="Paracetamol", quantity=2)],
        payment_method="Cash",
    )
    user = CurrentUser(id=1, username="adminroot", role="admin", permissions=["pos.checkout"])
    result = await PosService(session).process_checkout(payload, user)
    assert result.net_total == Decimal("20.00")
    assert result.tax_total == Decimal("2.80")
    assert result.total_amount == Decimal("22.80")
    assert await BatchRepository(session).sum_on_hand("Paracetamol") == 2


async def test_pos_checkout_not_found(session):
    payload = CheckoutRequest(
        line_items=[CheckoutLineIn(product_name="Nosuch", quantity=1)], payment_method="Cash"
    )
    user = CurrentUser(id=1, username="adminroot", role="admin", permissions=["pos.checkout"])
    with pytest.raises(NotFoundError):
        await PosService(session).process_checkout(payload, user)


async def test_pos_checkout_multi_terminal(monkeypatch, session):
    await _seed_product(session)
    await _receive(session, "Paracetamol", 4)
    monkeypatch.setattr(config_mod.settings, "multi_terminal", True)

    async def _raise(*_args, **_kwargs):
        raise RuntimeError("sync down")

    monkeypatch.setattr(SyncRepository, "append_outbox", _raise)
    payload = CheckoutRequest(
        line_items=[CheckoutLineIn(product_name="Paracetamol", quantity=1)], payment_method="Cash"
    )
    user = CurrentUser(id=1, username="adminroot", role="admin", permissions=["pos.checkout"])
    result = await PosService(session).process_checkout(payload, user)
    assert result.receipt_number.startswith("RCP-")


async def test_pos_record_drawer_movement(session, admin_user):
    payload = DrawerMovementCreate(amount=Decimal("50.00"), reason="cash-in", cashier="adminroot")
    user = CurrentUser(id=1, username="adminroot", role="admin", permissions=["pos.drawer"])
    result = await PosService(session).record_drawer_movement(payload, user)
    assert result.amount == Decimal("50.00")
    assert result.new_balance == Decimal("50.00")


async def test_pos_open_shift(session, admin_user):
    user = CurrentUser(id=1, username="adminroot", role="admin", permissions=["pos.drawer"])
    result = await PosService(session).open_shift(ShiftOpenRequest(opening_float=Decimal("100.00")), user)
    assert result.opening_float == Decimal("100.00")
    assert result.status == "open"


async def _open_and_seed_sales(session, admin_user, opening=Decimal("100.00")):
    user = CurrentUser(id=1, username="adminroot", role="admin", permissions=["pos.drawer"])
    shift = await PosService(session).open_shift(ShiftOpenRequest(opening_float=opening), user)
    session.add(
        Receipt(
            timestamp=shift.opened_at,
            total_amount=Decimal("250.00"),
            payment_method="Cash",
            server_created_at=shift.opened_at,
            created_by="adminroot",
            cashier_attribution="adminroot",
        )
    )
    session.add(
        DrawerMovement(
            cashier="adminroot",
            amount=Decimal("-150.00"),
            reason="paid_out",
            prior_balance=Decimal("0"),
            new_balance=Decimal("-150.00"),
            server_created_at=shift.opened_at,
            created_by="adminroot",
        )
    )
    await session.commit()
    return shift


async def test_pos_close_shift_not_found(session, admin_user):
    with pytest.raises(NotFoundError):
        await PosService(session).close_shift(
            ShiftCloseRequest(shift_id=9999, counted_cash=Decimal("0"))
        )


async def test_pos_close_shift_already_closed(session, admin_user):
    shift = await _open_and_seed_sales(session, admin_user)
    await PosService(session).close_shift(
        ShiftCloseRequest(shift_id=shift.id, counted_cash=Decimal("200.00"))
    )
    with pytest.raises(AppException):
        await PosService(session).close_shift(
            ShiftCloseRequest(shift_id=shift.id, counted_cash=Decimal("200.00"))
        )


async def test_pos_close_shift_success(session, admin_user):
    shift = await _open_and_seed_sales(session, admin_user)
    result = await PosService(session).close_shift(
        ShiftCloseRequest(shift_id=shift.id, counted_cash=Decimal("200.00"))
    )
    assert result.expected_cash == Decimal("200.00")
    assert result.variance == Decimal("0.00")


async def test_pos_preview_shift_not_found(session, admin_user):
    with pytest.raises(NotFoundError):
        await PosService(session).preview_shift(9999)


async def test_pos_preview_shift_success(session, admin_user):
    shift = await _open_and_seed_sales(session, admin_user)
    result = await PosService(session).preview_shift(shift.id)
    assert result.expected_cash == Decimal("200.00")


async def _seed_receipt_for_refund(session):
    receipt = Receipt(
        timestamp="2026-01-01T00:00:00",
        total_amount=Decimal("10.00"),
        payment_method="Cash",
        server_created_at="2026-01-01T00:00:00",
        created_by="adminroot",
        cashier_attribution="adminroot",
    )
    session.add(receipt)
    await session.flush()
    session.add(
        ReceiptItem(
            receipt_id=receipt.id,
            product_name="Paracetamol",
            quantity=2,
            price_at_time=Decimal("5.00"),
            internal_barcode="INT-PAR",
            vendor="Acme",
            expiry_date="2030-01-01",
        )
    )
    await session.commit()
    return receipt


async def test_pos_refund_not_found(session, admin_user):
    with pytest.raises(NotFoundError):
        await PosService(session).refund(
            RefundRequest(receipt_id=9999, reason="x"),
            CurrentUser(id=1, username="adminroot", role="admin", permissions=["pos.checkout"]),
        )


async def test_pos_refund_already_refunded(session, admin_user):
    receipt = await _seed_receipt_for_refund(session)
    user = CurrentUser(id=1, username="adminroot", role="admin", permissions=["pos.checkout"])
    await PosService(session).refund(RefundRequest(receipt_id=receipt.id, reason="bad"), user)
    with pytest.raises(AppException):
        await PosService(session).refund(RefundRequest(receipt_id=receipt.id, reason="bad2"), user)


async def test_pos_refund_success(session, admin_user):
    receipt = await _seed_receipt_for_refund(session)
    user = CurrentUser(id=1, username="adminroot", role="admin", permissions=["pos.checkout"])
    result = await PosService(session).refund(RefundRequest(receipt_id=receipt.id, reason="bad"), user)
    assert result.total_amount == Decimal("-10.00")
    assert await BatchRepository(session).sum_on_hand("Paracetamol") == 2


async def test_pos_sales_report(session, admin_user):
    session.add(
        Receipt(
            total_amount=Decimal("100.00"),
            payment_method="Cash",
            created_by="adminroot",
            cashier_attribution="adminroot",
            server_created_at="2026-01-01T00:00:00",
            timestamp="2026-01-01T00:00:00",
        )
    )
    session.add(
        Refund(
            receipt_id=0,
            total_amount=Decimal("-20.00"),
            reason="x",
            cashier="adminroot",
            server_created_at="2026-01-01T00:00:00",
        )
    )
    await session.commit()
    report = await PosService(session).sales_report()
    assert report.gross_revenue == Decimal("100.00")
    assert report.refund_total == Decimal("-20.00")
    assert report.net_revenue == Decimal("80.00")


# ─────────────────────────── Auth service ───────────────────────────


async def test_parse_locked_until_invalid(session, admin_user):
    assert _parse_locked_until("garbage") is None


async def test_authenticate_inactive(session, role_and_perms):
    user = await UserRepository(session).create(
        "inactive", "I", hash_password("Password123!@#"), role_and_perms.id
    )
    user.is_active = 0
    await session.commit()
    with pytest.raises(UnauthorizedError):
        await AuthService(session).authenticate("inactive", "Password123!@#")


async def test_authenticate_locked(session, admin_user):
    admin_user.locked_until = "2999-01-01T00:00:00+00:00"
    await session.commit()
    with pytest.raises(ForbiddenError):
        await AuthService(session).authenticate("adminroot", "Password123!@#")


async def test_authenticate_wrong_pw_lockout(session, admin_user):
    for _ in range(5):
        with pytest.raises(UnauthorizedError):
            await AuthService(session).authenticate("adminroot", "wrong-password")
    refreshed = await UserRepository(session).get_by_username("adminroot")
    assert refreshed.locked_until is not None


async def test_authenticate_success(session, admin_user):
    user = await AuthService(session).authenticate("adminroot", "Password123!@#")
    assert user.failed_attempts == 0
    assert user.locked_until is None


async def test_authenticate_legacy_upgrade(monkeypatch, session, role_and_perms):
    import app.services.auth_service as auth_mod

    user = await UserRepository(session).create(
        "legacy", "L", b"scrypt$legacyhash", role_and_perms.id
    )
    monkeypatch.setattr(auth_mod, "verify_password", lambda pw, h: True)
    monkeypatch.setattr(auth_mod, "upgrade_legacy_hash", lambda pw: b"$2$newbcrypthash")
    result = await AuthService(session).authenticate("legacy", "Password123!@#")
    assert result.password_hash == b"$2$newbcrypthash"


async def test_login_success(session, admin_user):
    token = await AuthService(session).login("adminroot", "Password123!@#")
    assert token.access_token and token.refresh_token


async def test_refresh_wrong_type(session, admin_user):
    from app.shared.security import create_access_token

    bad = create_access_token("1", "admin", [], username="adminroot")
    with pytest.raises(UnauthorizedError):
        await AuthService(session).refresh(bad)


async def test_refresh_unknown_user(session, admin_user):
    from app.shared.security import create_refresh_token

    with pytest.raises(UnauthorizedError):
        await AuthService(session).refresh(create_refresh_token("999999"))


async def test_refresh_success(session, admin_user):
    from app.shared.security import create_refresh_token

    token = await AuthService(session).refresh(create_refresh_token(str(admin_user.id)))
    assert token.access_token


async def test_register_conflict(session, admin_user):
    with pytest.raises(ConflictError):
        await AuthService(session).register(
            UserCreate(username="adminroot", password="Password123!@#", role_id=admin_user.role_id)
        )


async def test_register_weak_password(session, role_and_perms):
    with pytest.raises(AppException):
        await AuthService(session).register(
            UserCreate(username="weak", password="abcdefghij12", role_id=role_and_perms.id)
        )


async def test_register_success(session, role_and_perms):
    result = await AuthService(session).register(
        UserCreate(
            username="newbie", display_name="N", password="Password123!@#", role_id=role_and_perms.id
        )
    )
    assert result.username == "newbie"


async def test_set_pin_unknown(session):
    with pytest.raises(UnauthorizedError):
        await AuthService(session).set_pin("ghost", "1234")


async def test_set_pin_no_pepper(session, admin_user, monkeypatch):
    monkeypatch.setattr(auth_mod, "get_pin_pepper", lambda: _NoPepper())
    with pytest.raises(UnauthorizedError):
        await AuthService(session).set_pin("adminroot", "1234")


async def test_pin_login_not_found(session, pin_pepper):
    with pytest.raises(UnauthorizedError):
        await AuthService(session).pin_login("ghost", "1234")


async def test_pin_login_no_pepper(session, admin_user, monkeypatch):
    monkeypatch.setattr(auth_mod, "get_pin_pepper", lambda: _NoPepper())
    with pytest.raises(UnauthorizedError):
        await AuthService(session).pin_login("adminroot", "1234")


async def test_pin_login_success(session, admin_user, pin_pepper):
    await AuthService(session).set_pin("adminroot", "1234")
    token = await AuthService(session).pin_login("adminroot", "1234")
    assert token.access_token


async def test_pin_login_tampered(session, admin_user, pin_pepper):
    await AuthService(session).set_pin("adminroot", "1234")
    user = await UserRepository(session).get_by_username("adminroot")
    user.lockout_hmac = b"x" * 32
    await session.commit()
    with pytest.raises(ForbiddenError):
        await AuthService(session).pin_login("adminroot", "1234")


async def test_pin_login_locked(session, admin_user, pin_pepper):
    await AuthService(session).set_pin("adminroot", "1234")
    user = await UserRepository(session).get_by_username("adminroot")
    user.pin_locked_until = "2999-01-01T00:00:00+00:00"
    await session.commit()
    with pytest.raises(ForbiddenError):
        await AuthService(session).pin_login("adminroot", "1234")


async def test_pin_login_wrong_then_lockout(session, admin_user, pin_pepper):
    await AuthService(session).set_pin("adminroot", "1234")
    for _ in range(5):
        with pytest.raises(UnauthorizedError):
            await AuthService(session).pin_login("adminroot", "0000")
    user = await UserRepository(session).get_by_username("adminroot")
    assert user.pin_locked_until is not None


async def test_approve_action_unknown(session, pin_pepper):
    with pytest.raises(UnauthorizedError):
        await AuthService(session).approve_action("ghost", "1234", "drawer.move")


async def test_approve_action_no_pepper(session, admin_user):
    set_pin_pepper(None)
    with pytest.raises(UnauthorizedError):
        await AuthService(session).approve_action("adminroot", "1234", "drawer.move")


async def test_approve_action_tampered(session, admin_user, pin_pepper):
    await AuthService(session).set_pin("adminroot", "1234")
    user = await UserRepository(session).get_by_username("adminroot")
    user.lockout_hmac = b"x" * 32
    await session.commit()
    with pytest.raises(ForbiddenError):
        await AuthService(session).approve_action("adminroot", "1234", "drawer.move")


async def test_approve_action_locked(session, admin_user, pin_pepper):
    await AuthService(session).set_pin("adminroot", "1234")
    user = await UserRepository(session).get_by_username("adminroot")
    user.pin_locked_until = "2999-01-01T00:00:00+00:00"
    await session.commit()
    with pytest.raises(ForbiddenError):
        await AuthService(session).approve_action("adminroot", "1234", "drawer.move")


async def test_approve_action_wrong_pin(session, admin_user, pin_pepper):
    await AuthService(session).set_pin("adminroot", "1234")
    with pytest.raises(UnauthorizedError):
        await AuthService(session).approve_action("adminroot", "0000", "drawer.move")


async def test_approve_action_success(session, admin_user, pin_pepper):
    await AuthService(session).set_pin("adminroot", "1234")
    token = await AuthService(session).approve_action("adminroot", "1234", "drawer.move")
    assert token


# ─────────────────────────── Inventory service ───────────────────────────


async def test_fifo_recalled(session):
    await _seed_product(session)
    await _receive(session, "Paracetamol", 1)
    lot = (await BatchRepository(session).get_lots_for_product("Paracetamol"))[0]
    lot.recalled = 1
    await session.commit()
    with pytest.raises(RecalledLotError):
        await InventoryService(session).fifo_deduct("Paracetamol", 1)


async def test_fifo_expired(session):
    await _seed_product(session)
    await _receive(session, "Paracetamol", 1, expiry="2000-01-01")
    with pytest.raises(ExpiredLotError):
        await InventoryService(session).fifo_deduct("Paracetamol", 1)


async def test_fifo_missing(session):
    with pytest.raises(MissingLotError):
        await InventoryService(session).fifo_deduct("Nosuch", 1)


async def test_fifo_oversell(session):
    await _seed_product(session)
    await _receive(session, "Paracetamol", 2)
    with pytest.raises(OverSellError):
        await InventoryService(session).fifo_deduct("Paracetamol", 5)


async def test_return_stock_zero(session):
    await InventoryService(session).return_stock("Nosuch", 0)


async def test_return_stock_new_lot(session):
    await InventoryService(session).return_stock("Paracetamol", 3)
    lots = await BatchRepository(session).get_lots_for_product("Paracetamol")
    assert len(lots) == 1 and lots[0].on_hand == 3


async def test_return_stock_existing(session):
    await _seed_product(session)
    await _receive(session, "Paracetamol", 2)
    await InventoryService(session).return_stock("Paracetamol", 1)
    assert await BatchRepository(session).sum_on_hand("Paracetamol") == 3


async def test_low_stock_override(session):
    session.add(
        Product(
            name="Low",
            price=Decimal("1"),
            internal_unique_barcode="INT-LOW",
            vendor_name="Acme",
            expiry_date="2030-01-01",
            reorder_threshold=5,
        )
    )
    await InventoryService(session).receive_batch("Low", "L1", "2030-01-01", 2, 1.0, "Acme")
    await session.commit()
    result = await InventoryService(session).low_stock(threshold_override=10)
    assert any(p.name == "Low" for p in result)


async def test_expiring_soon(session):
    session.add(InventoryExtended(drug_name="Exp", on_hand=1, expiration_date="2026-09-01"))
    await session.commit()
    result = await InventoryService(session).expiring_soon(days=90)
    assert any(b.drug_name == "Exp" for b in result)


async def test_stock_levels(session):
    session.add(
        Product(
            name="Lev",
            price=Decimal("1"),
            internal_unique_barcode="INT-LEV",
            vendor_name="Acme",
            expiry_date="2030-01-01",
            reorder_threshold=5,
        )
    )
    await InventoryService(session).receive_batch("Lev", "L1", "2030-01-01", 2, 1.0, "Acme")
    await session.commit()
    result = await InventoryService(session).stock_levels()
    assert any(s.name == "Lev" for s in result)


async def test_get_batch_not_found(session):
    with pytest.raises(NotFoundError):
        await InventoryService(session).get_batch(9999)


async def test_adjust_batch_negative(session):
    with pytest.raises(ValidationError):
        await InventoryService(session).adjust_batch(1, BatchUpdate(on_hand=-1))


async def test_adjust_batch_not_found(session):
    with pytest.raises(NotFoundError):
        await InventoryService(session).adjust_batch(9999, BatchUpdate(on_hand=5))


async def test_adjust_batch_ok(session):
    await _seed_product(session)
    await _receive(session, "Paracetamol", 2)
    lot = (await BatchRepository(session).get_lots_for_product("Paracetamol"))[0]
    result = await InventoryService(session).adjust_batch(lot.id, BatchUpdate(on_hand=10))
    assert result.on_hand == 10


# ─────────────────────────── Sync service ───────────────────────────


async def test_sync_push_dedup_and_oversell(session):
    session.add(SyncInventory(product_name="Paracetamol", on_hand=10))
    session.add(SyncInventory(product_name="Ibuprofen", on_hand=0))
    await session.commit()
    svc = SyncService(session)
    normal = SyncPushEntry(
        device_id="d1",
        local_seq=1,
        client_txn_id="n1",
        payload={"items": [{"product_name": "Paracetamol", "quantity": 1}]},
    )
    oversell = SyncPushEntry(
        device_id="d1",
        local_seq=2,
        client_txn_id="o1",
        payload={"items": [{"product_name": "Ibuprofen", "quantity": 1}]},
    )
    skip = SyncPushEntry(
        device_id="d1",
        local_seq=3,
        client_txn_id="s1",
        payload={"items": [{"product_name": "Paracetamol", "quantity": 0}]},
    )
    first = await svc.push([normal, oversell, skip])
    assert first.accepted == 3 and first.over_sells == 1
    again = await svc.push([normal])
    assert again.deduped == 1 and again.accepted == 0


async def test_sync_list_discrepancies(session):
    await SyncRepository(session).insert_discrepancy("OVER_SOLD_CROSS_TERMINAL", "d1", 2, "o1", "x")
    await session.commit()
    rows = await SyncService(session).list_discrepancies()
    assert any(d.client_txn_id == "o1" for d in rows)


async def test_sync_resolve_not_found(session):
    with pytest.raises(NotFoundError):
        await SyncService(session).resolve_discrepancy(99999)
