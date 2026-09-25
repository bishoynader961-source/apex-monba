"""Unit tests for app.core.ttl_cache (Phase 3 caching strategy)."""
from __future__ import annotations

import time

from app.core.ttl_cache import (
    cache_clear,
    cache_get,
    cache_invalidate,
    cache_invalidate_prefix,
    cache_set,
)


def setup_function() -> None:
    cache_clear()


def teardown_function() -> None:
    cache_clear()


def test_set_and_get_roundtrip() -> None:
    assert cache_get("missing") is None
    cache_set("k", {"a": 1})
    assert cache_get("k") == {"a": 1}


def test_expiry_is_honoured() -> None:
    cache_set("k", "v", ttl_seconds=0.01)
    assert cache_get("k") == "v"
    time.sleep(0.02)
    assert cache_get("k") is None


def test_invalidate_single_key() -> None:
    cache_set("a", 1)
    cache_set("b", 2)
    cache_invalidate("a")
    assert cache_get("a") is None
    assert cache_get("b") == 2
    cache_invalidate("nope")  # no-op, must not raise


def test_invalidate_prefix() -> None:
    cache_set("perms:1", ("admin", ["*"]))
    cache_set("perms:2", ("pharm", ["inventory.read"]))
    cache_set("settings:list", [])
    cache_invalidate_prefix("perms:")
    assert cache_get("perms:1") is None
    assert cache_get("perms:2") is None
    assert cache_get("settings:list") == []
