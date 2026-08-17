from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.shared.schemas import LoginRequest, ProductRead, Token, UserCreate, UserPublic


def test_login_request_validation() -> None:
    LoginRequest(username="a", password="b")
    with pytest.raises(ValidationError):
        LoginRequest()  # type: ignore[call-arg]


def test_user_create_requires_long_password() -> None:
    with pytest.raises(ValidationError):
        UserCreate(username="x", password="short")
    with pytest.raises(ValidationError):
        UserCreate(username="x", password="123")


def test_product_read_from_attributes() -> None:
    class Row:
        id = 1
        name = "Ibuprofen"
        price = 3.5
        manufacturer_barcode = ""
        internal_unique_barcode = "MED-1"
        status = "In Stock"
        expiry_date = ""
        manufacture_date = ""
        vendor_name = "DrugDirect"
        dea_schedule = None
        wholesale_price = None
        reorder_threshold = None

    model = ProductRead.model_validate(Row())
    assert model.name == "Ibuprofen" and model.id == 1


def test_token_shape() -> None:
    Token(
        access_token="a",
        refresh_token="b",
        user=UserPublic(id=1, username="u", display_name="U", role_id=3),
    )
