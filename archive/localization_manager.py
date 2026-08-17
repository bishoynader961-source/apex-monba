import os
import json
import locale
import logging
import threading
try:
    import requests
except Exception:
    requests = None

log = logging.getLogger("localization_manager")

import i18n as _i18n

_REGIONS = {
    "US": {
        "display_name": "United States",
        "currency_symbol": "$",
        "currency_code": "USD",
        "symbol_position": "prefix",
        "decimal_sep": ".",
        "thousands_sep": ",",
        "tax_term": "Sales Tax",
        "date_format": "%m/%d/%Y",
        "drug_code_label": "NDC",
        "vat_label": "Sales Tax",
    },
    "GB": {
        "display_name": "United Kingdom",
        "currency_symbol": "\u00a3",
        "currency_code": "GBP",
        "symbol_position": "prefix",
        "decimal_sep": ".",
        "thousands_sep": ",",
        "tax_term": "VAT",
        "date_format": "%d/%m/%Y",
        "drug_code_label": "PIP Code",
        "vat_label": "VAT",
    },
    "DE": {
        "display_name": "Germany",
        "currency_symbol": "\u20ac",
        "currency_code": "EUR",
        "symbol_position": "suffix",
        "decimal_sep": ",",
        "thousands_sep": ".",
        "tax_term": "MwSt.",
        "date_format": "%d.%m.%Y",
        "drug_code_label": "PZN",
        "vat_label": "MwSt.",
    },
}

_VALID_REGIONS = {"US", "GB", "DE"}


_REGION_BY_LOCALE = {
    "en-us": "US", "en_us": "US", "en-US": "US",
    "en-gb": "GB", "en_gb": "GB", "en-GB": "GB",
    "en-ie": "GB", "en_ie": "GB",
    "de-de": "DE", "de_de": "DE", "de-DE": "DE",
    "de-at": "DE", "de_at": "DE",
    "de-lu": "DE", "de_lu": "DE",
    "fr-lu": "DE",
}

_REGION_BY_COUNTRY = {
    "US": "US", "GB": "GB", "UK": "GB", "DE": "DE",
    "AT": "DE", "LU": "DE",
}


def get_regions():
    return dict(_REGIONS)


def get_region_info(code):
    return _REGIONS.get(code, _REGIONS["US"])


def _load_config():
    try:
        import database as db
        return db.load_config()  # if exists; else fallback
    except Exception:
        pass
    try:
        import barcode_logic
        return barcode_logic.load_config()
    except Exception:
        return {}


def _read_region_override():
    try:
        import rx_config
        return rx_config.ConfigManager().get_region()
    except Exception:
        return None


def _read_autodetect_flag():
    cfg = _load_config()
    return cfg.get("region_autodetect", True)


def _os_locale_region():
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(85)
        if ctypes.windll.kernel32.GetUserDefaultLocaleName(buf, 85):
            raw = buf.value  # e.g. en-GB, de-DE
            return _REGION_BY_LOCALE.get(raw.lower(), _REGION_BY_COUNTRY.get(raw.split("-")[-1].upper()))
    except Exception:
        pass
    try:
        loc = locale.getlocale()[0]
        if loc:
            code = loc.split("_")[0].upper()
            return _REGION_BY_LOCALE.get(loc.lower(), _REGION_BY_COUNTRY.get(code))
    except Exception:
        pass
    lang = os.environ.get("LANG", "")
    if lang:
        return _REGION_BY_LOCALE.get(lang.lower(), _REGION_BY_COUNTRY.get(lang.split("_")[-1].upper()))
    return None


def _ip_geolocate_region():
    if not _read_autodetect_flag():
        return None
    if requests is None:
        return None
    try:
        resp = requests.get("https://ipapi.co/json/", timeout=2)
        if resp.status_code != 200:
            raise RuntimeError(f"IP endpoint returned {resp.status_code}")
        data = resp.json()
        country = data.get("country", "") or ""
        region = _REGION_BY_COUNTRY.get(country.upper())
        if region not in _VALID_REGIONS:
            log.debug("IP geolocation returned unknown region %r (country=%s), falling back to US", region, country)
            return None
        return region
    except Exception as e:
        log.debug("IP geolocation failed: %s", e)
        return None


def detect_region():
    override = _read_region_override()
    if override:
        return override
    cached = _read_cached_geolocation()
    if cached:
        return cached
    os_region = _os_locale_region()
    if os_region:
        return os_region
    ip_region = _ip_geolocate_region()
    if ip_region:
        _cache_geolocation(ip_region)
        return ip_region
    return "US"


_CACHE_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "archive", ".region_cache.json")


def _read_cached_geolocation():
    try:
        if os.path.exists(_CACHE_FILE):
            with open(_CACHE_FILE, "r") as f:
                data = json.load(f)
            region = data.get("region")
            ts = data.get("timestamp", 0)
            import time
            if region and (time.time() - ts) < 86400:
                return region
    except Exception:
        return None
    return None


def _cache_geolocation(region):
    try:
        import time
        with open(_CACHE_FILE, "w") as f:
            json.dump({"region": region, "timestamp": time.time()}, f)
    except Exception:
        pass


class LocalizationManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, app_root=None):
        if self._initialized:
            if app_root is not None:
                self._app_root = app_root
            return
        import database as db
        self._db = db
        self._app_root = app_root
        self._listeners = []
        self._broadcasting = False
        self._region = None
        self._init_region()
        self._initialized = True

    def _init_region(self):
        self._region = _read_region_override() or detect_region()

    def region(self):
        return self._region

    def display_region(self):
        return get_region_info(self._region)["display_name"]

    def display_region_label(self):
        return f"{get_region_info(self._region)['display_name']} ({self.currency_code()})"

    def currency_symbol(self):
        return get_region_info(self._region)["currency_symbol"]

    def currency_code(self):
        return get_region_info(self._region)["currency_code"]

    def tax_term(self):
        return get_region_info(self._region)["tax_term"]

    def date_format(self):
        return get_region_info(self._region)["date_format"]

    def drug_code_label(self):
        return get_region_info(self._region)["drug_code_label"]

    def vat_label(self):
        return get_region_info(self._region)["vat_label"]

    def format_money(self, value, *, with_symbol=True):
        info = get_region_info(self._region)
        if value is None:
            value = 0.0
        try:
            value = float(value)
        except (TypeError, ValueError):
            value = 0.0
        if info["symbol_position"] == "suffix":
            number = f"{value:,.2f}".replace(",", "§").replace(".", info["decimal_sep"]).replace("§", info["thousands_sep"])
            if with_symbol:
                return f"{number} {info['currency_symbol']}"
            return number
        else:
            number = f"{value:,.2f}".replace(",", "§").replace(".", info["decimal_sep"]).replace("§", info["thousands_sep"])
            if with_symbol:
                return f"{info['currency_symbol']}{number}"
            return number

    def parse_money(self, text):
        if text is None:
            return 0.0
        s = str(text).strip()
        info = get_region_info(self._region)
        s = s.replace(info["currency_symbol"], "")
        s = s.replace(info["thousands_sep"], "")
        s = s.replace(info["decimal_sep"], ".")
        s = s.replace(",", "").replace(".", ".") if info["decimal_sep"] == "." else s
        try:
            return float(s)
        except ValueError:
            return 0.0

    def format_date(self, iso_date_str):
        if not iso_date_str:
            return ""
        try:
            from datetime import datetime
            dt = datetime.strptime(iso_date_str.split("T")[0], "%Y-%m-%d")
            return dt.strftime(self.date_format())
        except Exception:
            return iso_date_str

    def set_region(self, code, *, notify=True):
        code = self._normalize(code)
        old = self._region
        self._region = code
        try:
            self._db.set_kv("region", code)
        except Exception as e:
            log.warning("set_kv(region) failed: %s", e)
        if notify and old != code:
            self._broadcast(old, code)

    def _normalize(self, code):
        return "GB" if str(code).upper() in ("UK", "GB") else (code or "US")

    def register_listener(self, cb):
        self._listeners.append(cb)
        try:
            cb(self._region, self._region)
        except Exception as e:
            log.warning("listener initial fire failed: %s", e)

    def unregister_listener(self, cb):
        if cb in self._listeners:
            self._listeners.remove(cb)

    def _broadcast(self, old, new):
        if self._broadcasting:
            return
        self._broadcasting = True
        try:
            for cb in list(self._listeners):
                try:
                    cb(old, new)
                except Exception as e:
                    log.warning("region listener error: %s", e)
        finally:
            self._broadcasting = False
        if self._app_root and hasattr(self._app_root, "after_idle"):
            self._app_root.after_idle(self._apply_to_open_toplevels, old, new)

    def _apply_to_open_toplevels(self, old, new):
        try:
            if self._app_root is None:
                return
            for w in self._app_root.winfo_toplevel() if hasattr(self._app_root, "winfo_toplevel") else []:
                pass
        except Exception:
            pass

    def refresh_all(self):
        for cb in list(self._listeners):
            try:
                cb(self._region, self._region)
            except Exception as e:
                log.warning("refresh_all listener error: %s", e)

    def is_banner_dismissed(self, region=None):
        region = region or self._region
        try:
            rec = self._db.get_kv("region_banner_region", "")
        except Exception:
            rec = ""
        if rec != region:
            return False
        try:
            return self._db.get_kv("region_banner_dismissed", "0") == "1"
        except Exception:
            return False

    def set_banner_dismissed(self, region, dismissed=True):
        region = self._normalize(region)
        self._db.set_kv("region_banner_region", region)
        self._db.set_kv("region_banner_dismissed", "1" if dismissed else "0")

    def get_field_visibility(self):
        # Canonical key set — every region returns the same keys so callers can
        # index any field without guarding for KeyError.
        base = {
            "dea_number": False, "npi": False, "nhs_number": False,
            "gphc_number": False, "exemption_category": False, "pzn_code": False,
            "insurance_bin": False, "insurance_pcn": False, "scheme_pcn": False,
            "group_number": False,
        }
        if self._region == "US":
            base.update({"dea_number": True, "npi": True, "insurance_bin": True,
                         "insurance_pcn": True, "group_number": True})
        elif self._region == "GB":
            base.update({"nhs_number": True, "exemption_category": True,
                         "gphc_number": True, "scheme_pcn": True})
        else:  # DE
            base.update({"pzn_code": True})
        return base

    def visible_fields(self):
        """Return the ordered list of region-specific field keys to show."""
        vis = self.get_field_visibility()
        order = ["dea_number", "npi", "nhs_number", "gphc_number",
                 "exemption_category", "pzn_code", "insurance_bin",
                 "insurance_pcn", "scheme_pcn", "group_number"]
        return [k for k in order if vis.get(k)]

    def field_label(self, key: str) -> str:
        """Localized label for a region-specific identifier field key."""
        return _i18n.t("field_" + key)


_manager = None


def init(app_root=None):
    global _manager
    if _manager is None:
        _manager = LocalizationManager(app_root=app_root)
    elif app_root is not None:
        _manager._app_root = app_root
    return _manager


def get_manager():
    global _manager
    if _manager is None:
        _manager = LocalizationManager()
    return _manager
