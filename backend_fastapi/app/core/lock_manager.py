"""Per-drug concurrency primitives shared by POS checkout and inventory adjustment.

Extracted from ``PosService`` to break the ``pos_service`` <-> ``inventory_service``
import cycle: both modules import this dependency-free module instead of each other.

Locks are ``asyncio.Lock`` (single-process). For multi-worker deployments a DB
advisory/Redis lock would be required (see plan §15.3 — out of scope, matches the
existing single-process checkout-lock architecture).
"""
from __future__ import annotations

import asyncio
from collections import OrderedDict
from contextlib import asynccontextmanager
from typing import AsyncIterator

# Bounded LRU of per-drug locks: one entry per distinct drug-name, evicted oldest
# first once over capacity. A currently-held lock is NEVER evicted — correctness
# over memory (a held lock guards an in-flight checkout/adjust). This bounds the
# otherwise-unbounded growth of the hot-path lock cache on long-running kiosks
# (TASK 3, Fix B).
_LOCK_MAXSIZE: int = 4096

_locks: "OrderedDict[str, asyncio.Lock]" = OrderedDict()
_registry_lock = asyncio.Lock()


def _evict_lock() -> None:
    """Evict the oldest UNHELD entry to stay within ``_LOCK_MAXSIZE``.

    Iterates oldest-first; skips (keeps) any held lock. If every entry is held,
    no eviction occurs and the dict may temporarily exceed the cap — correctness
    takes priority over the memory bound.
    """
    for name, lock in list(_locks.items()):
        if len(_locks) <= _LOCK_MAXSIZE:
            break
        if not lock.locked():
            del _locks[name]


def reset_locks() -> None:
    """Clear all locks — used by tests to ensure isolation between event loops."""
    _locks.clear()
    global _registry_lock
    _registry_lock = asyncio.Lock()


async def get_lock(name: str) -> asyncio.Lock:
    """Return (creating if necessary) the shared lock for ``name``.

    Used by ``PosService.process_checkout`` which acquires multiple locks in a
    deterministic (sorted) order and releases them in a ``finally`` block.
    The cache is an LRU: a hit moves ``name`` to the most-recent end, and the
    cache is trimmed to ``_LOCK_MAXSIZE`` (evicting only unheld locks).
    """
    async with _registry_lock:
        lock = _locks.get(name)
        if lock is None:
            lock = asyncio.Lock()
            _locks[name] = lock
        else:
            _locks.move_to_end(name)
        _evict_lock()
        return lock


@asynccontextmanager
async def acquire_drug_lock(name: str) -> AsyncIterator[None]:
    """Acquire the shared per-drug lock for ``name`` for the duration of the block.

    Used by ``InventoryService.adjust_batch`` (single lock; no ordering needed).
    Checkout uses ``get_lock`` directly because it must acquire a sorted set of
    locks atomically (handled by its own acquire/release loop).
    """
    lock = await get_lock(name)
    await lock.acquire()
    try:
        yield
    finally:
        if lock.locked():
            lock.release()
