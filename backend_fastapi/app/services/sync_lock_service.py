"""Distributed sync lock service (Tier-3 concurrency control, §2.1).

Manages in-process distributed locks for multi-client sync serialization.
Locks are keyed by a resource name (e.g. ``"sync"``) and expire after ``ttl_seconds``.
Each lock records the holder's ``device_id``, a ``nonce``, and an ``expires_at`` timestamp.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from app.shared.logging_config import get_logger

logger = get_logger("sync_lock")

_LOCK_LEASE_TTL_FALLBACK = 30


@dataclass
class LockEntry:
    device_id: str
    nonce: str
    expires_at: float  # epoch seconds


class SyncLockService:
    """In-process distributed lock backed by an asyncio-protected dict.

    For multi-worker deployments a DB advisory or Redis lock would be required
    (see plan §15.3 — out of scope, matches the existing single-process architecture).
    """

    def __init__(self) -> None:
        self._locks: dict[str, LockEntry] = {}
        self._mutex = asyncio.Lock()

    @staticmethod
    def _now() -> float:
        return time.time()

    @staticmethod
    def _expiry_ts(ttl_seconds: int) -> float:
        return time.time() + ttl_seconds

    async def acquire(self, resource: str, device_id: str, nonce: str, ttl_seconds: int) -> LockEntry:
        async with self._mutex:
            existing = self._locks.get(resource)
            if existing and existing.expires_at > self._now():
                if existing.nonce != nonce:
                    logger.info("lock.acquired_denied", resource=resource, holder=existing.device_id)
                    return existing
            self._locks[resource] = LockEntry(
                device_id=device_id,
                nonce=nonce,
                expires_at=self._expiry_ts(ttl_seconds),
            )
            logger.info("lock.acquired", resource=resource, device_id=device_id)
            return self._locks[resource]

    async def release(self, resource: str, nonce: str) -> bool:
        async with self._mutex:
            existing = self._locks.get(resource)
            if existing and existing.nonce == nonce:
                del self._locks[resource]
                logger.info("lock.released", resource=resource)
                return True
            return False

    async def heartbeat(self, resource: str, nonce: str, ttl_seconds: int) -> bool:
        async with self._mutex:
            existing = self._locks.get(resource)
            if existing and existing.nonce == nonce and existing.expires_at > self._now():
                existing.expires_at = self._expiry_ts(ttl_seconds)
                logger.info("lock.heartbeat", resource=resource)
                return True
            return False

    async def status(self, resource: str) -> Optional[LockEntry]:
        async with self._mutex:
            existing = self._locks.get(resource)
            if existing and existing.expires_at <= self._now():
                del self._locks[resource]
                return None
            return existing


_lock_service: Optional[SyncLockService] = None


def get_lock_service() -> SyncLockService:
    global _lock_service
    if _lock_service is None:
        _lock_service = SyncLockService()
    return _lock_service
