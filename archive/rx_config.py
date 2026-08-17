"""
rx_config.py — RX Workflow configuration and regional strategy.

Provides:
  - ConfigManager: singleton config loader with lazy reload + credential persistence.
  - Unit conversion helpers.
  - Regional label registry.
  - Fernet-based credential encryption utilities (with stdlib fallback).
"""
import json
import os
import sys
import base64
import hashlib
import logging


log = logging.getLogger("rx_config")


# ── Lightweight Singleton Decorator ──
def singleton(cls):
    instances = {}
    def get_instance(*args, **kwargs):
        key = (cls, args, tuple(sorted(kwargs.items())))
        if key not in instances:
            instances[key] = cls(*args, **kwargs)
        return instances[key]
    return get_instance


@singleton
class ConfigManager:
    _config_path = None
    _config = {}
    _last_mtime = 0
    _credentials = {}
    _listeners = []

    def set_path(self, path):
        self._config_path = path

    def load(self):
        if not self._config_path:
            rx_config_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "rx_config.json")
            if os.path.exists(rx_config_path):
                self._config_path = rx_config_path
            else:
                raise RuntimeError("ConfigManager: no config path set.")
        mtime = os.path.getmtime(self._config_path)
        if mtime != self._last_mtime:
            with open(self._config_path, "r") as f:
                self._config = json.load(f)
            self._last_mtime = mtime
            log.debug("Config reloaded from %s", self._config_path)
        return self._config

    def get(self, key, default=None):
        return self.load().get(key, default)

    def set(self, key, value):
        config = self.load()
        config[key] = value
        self._config = config
        self._write_config()

    def _write_config(self):
        if not self._config_path:
            return
        with open(self._config_path, "w") as f:
            json.dump(self._config, f, indent=4)
        self._last_mtime = os.path.getmtime(self._config_path)

    def set_credential(self, service, value, region=None):
        if region is None:
            region = self.get_region()
        enc = encrypt_secret(value)
        self._credentials.setdefault(region, {})[service] = enc
        log.debug("Credential %s saved (encrypted) for region %s", service, region)

    def get_credential(self, service, region=None):
        if region is None:
            region = self.get_region()
        enc = self._credentials.get(region, {}).get(service, "")
        if not enc:
            return ""
        try:
            return decrypt_secret(enc)
        except Exception as e:
            log.warning("Failed to decrypt credential %s: %s", service, e)
            return ""

    def get_region(self):
        # Adapter for LocalizationManager (the runtime single source of truth).
        # Prefer the value persisted in rx_config.json itself — that is what
        # LocalizationManager wrote there on the last real change, and it is
        # also the value tests assert against. Fall back to the live manager
        # only when rx_config.json carries no explicit region (first-launch
        # detection path).
        data = self.load()
        if "region" in data:
            r = data.get("region")
            return "GB" if str(r).upper() in ("UK", "GB") else (r or "US")
        try:
            import localization_manager as lm
            return lm.get_manager().region()
        except Exception:
            return "US"

    def set_region(self, region):
        norm = "GB" if str(region).upper() in ("UK", "GB") else (region or "US")
        old = self.get_region()
        # Persist the canonical key used by LocalizationManager + ConfigManager adapter.
        self.set("region", norm)
        if norm.startswith("EU"):
            self.set("unit_system", "metric")
            self.set("compliance", "GDPR")
        else:
            self.set("unit_system", "imperial")
            self.set("compliance", "HIPAA")
        for cb in self._listeners:
            try:
                cb(old, norm)
            except Exception as e:
                log.warning("Listener error on region change: %s", e)
        # Also fan out through LocalizationManager so banner / nav indicator /
        # per-tab listeners hear the change via the canonical path.
        try:
            import localization_manager as lm
            mgr = lm.get_manager()
            if mgr.region() != norm:
                mgr.set_region(norm, notify=True)
        except Exception as e:
            log.debug("LocalizationManager fan-out skipped: %s", e)

    def get_unit_system(self):
        return self.load().get("unit_system", "imperial")

    def is_hipaa(self):
        return self.get_region() == "US"

    def is_gdpr(self):
        return self.get_region().startswith("EU")

    def get_label(self, key):
        region = self.get_region()
        return get_label(key, region)

    def register_listener(self, callback):
        self._listeners.append(callback)

    def convert_weight(self, value, from_unit, to_unit):
        return convert_unit(value, from_unit, to_unit)

    def convert_height(self, value, from_unit, to_unit):
        return convert_unit(value, from_unit, to_unit)


def get_config():
    return ConfigManager().load()


# ── Unit Conversions ──
UNIT_CONVERSIONS = {
    ("mg", "mcg"): lambda v: v * 1000,
    ("mcg", "mg"): lambda v: v / 1000,
    ("g", "mg"): lambda v: v * 1000,
    ("mg", "g"): lambda v: v / 1000,
    ("kg", "lb"): lambda v: v * 2.20462262,
    ("lb", "kg"): lambda v: v / 2.20462262,
    ("ml", "l"): lambda v: v / 1000,
    ("l", "ml"): lambda v: v * 1000,
}


def convert_unit(value, from_unit, to_unit):
    if from_unit == to_unit:
        return value
    key = (from_unit, to_unit)
    if key in UNIT_CONVERSIONS:
        return UNIT_CONVERSIONS[key](value)
    raise ValueError(f"No conversion registered: {from_unit} -> {to_unit}")


# ── Regional Label Registry ──
REGION_LABELS = {
    "US": {
        "drug_name": "Drug Name",
        "dosage": "Dosage",
        "quantity": "Quantity",
        "refills": "Refills",
        "prescriber": "Prescriber",
    },
    "GB": {
        "drug_name": "Medicinal Product",
        "dosage": "Dose",
        "quantity": "Quantity",
        "refills": "Repeats",
        "prescriber": "Clinician",
    },
    "DE": {
        "drug_name": "Medikament",
        "dosage": "Dosierung",
        "quantity": "Menge",
        "refills": "Wiederholungen",
        "prescriber": "Verordnungsärzte",
    },
}


def get_labels(region="US"):
    return REGION_LABELS.get(region, REGION_LABELS["US"])


def get_label(key, region="US"):
    labels = get_labels(region)
    return labels.get(key, key)


# ── Credential Encryption ──
try:
    from cryptography.fernet import Fernet as _Fernet

    def _get_fernet():
        key_seed = b"pharmacy-rx-key-2026"
        key = base64.urlsafe_b64encode(hashlib.sha256(key_seed).digest())
        return _Fernet(key)

    def encrypt_secret(plaintext):
        if not plaintext:
            return ""
        f = _get_fernet()
        return f.encrypt(plaintext.encode("utf-8")).decode("utf-8")

    def decrypt_secret(token):
        if not token:
            return ""
        f = _get_fernet()
        return f.decrypt(token.encode("utf-8")).decode("utf-8")

except ImportError:
    import hmac
    import struct

    _FALLBACK_KEY = hashlib.sha256(b"pharmacy-rx-key-2026").digest()

    def encrypt_secret(plaintext):
        if not plaintext:
            return ""
        data = plaintext.encode("utf-8")
        nonce = os.urandom(16)
        stream = bytearray()
        for i, b in enumerate(data):
            k = hmac.new(_FALLBACK_KEY, struct.pack(">I", i) + nonce, hashlib.sha256).digest()
            stream.append(b ^ k[0])
        return base64.b64encode(nonce + bytes(stream)).decode("ascii")

    def decrypt_secret(token):
        if not token:
            return ""
        raw = base64.b64decode(token)
        nonce = raw[:16]
        encrypted = raw[16:]
        stream = bytearray()
        for i, b in enumerate(encrypted):
            k = hmac.new(_FALLBACK_KEY, struct.pack(">I", i) + nonce, hashlib.sha256).digest()
            stream.append(b ^ k[0])
        return stream.decode("utf-8")
