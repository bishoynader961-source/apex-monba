"""currency.py — region-aware money helpers for PharmacyPro.

Every pharmacy-facing money string MUST go through :class:`CurrencyFormatter`
instead of hardcoding ``$``. The formatter reads its region from
``LocalizationManager`` (the single source of truth) and produces strings
such as ``$1,234.50`` (US), ``£1,234.50`` (GB) or ``1.234,50 €`` (DE).

Tabs access it via ``self.app.currency`` (wired in ``PharmacyApp.__init__``),
so tab modules need no import of ``localization_manager`` and therefore no
import-cycle risk.
"""
import logging

log = logging.getLogger("currency")

_lm_cache = None
_formatter = None


def _lm():
    global _lm_cache
    if _lm_cache is None:
        try:
            import localization_manager as lm
            _lm_cache = lm.get_manager()
        except Exception as e:
            log.debug("LocalizationManager unavailable, defaulting to US: %s", e)
            return None
    return _lm_cache


class CurrencyFormatter:
    """Wraps LocalizationManager formatting for ergonomic use in views."""

    def __init__(self, manager=None):
        self._mgr = manager or _lm()

    def _m(self):
        m = self._mgr
        if m is None:
            m = _lm()
            if m is None:
                return None
            self._mgr = m
        return m

    def fmt(self, value, with_symbol=True):
        m = self._m()
        if m is None:
            try:
                return f"${float(value):,.2f}"
            except Exception:
                return "$0.00"
        return m.format_money(value, with_symbol=with_symbol)

    def parse(self, text):
        m = self._m()
        if m is None:
            try:
                s = str(text).replace("$", "").replace(",", "").strip()
                return float(s)
            except (TypeError, ValueError):
                return 0.0
        return m.parse_money(text)

    def symbol(self):
        m = self._m()
        if m is None:
            return "$"
        return m.currency_symbol()

    def tax_term(self):
        m = self._m()
        if m is None:
            return "Tax"
        return m.tax_term()

    def fmt_date(self, iso_date_str):
        m = self._m()
        if m is None:
            return iso_date_str or ""
        return m.format_date(iso_date_str)


def get_currency():
    """Module-level accessor used by modules that have no `app` reference."""
    global _formatter
    if _formatter is None:
        _formatter = CurrencyFormatter()
    return _formatter


def fmt(value, with_symbol=True):
    return get_currency().fmt(value, with_symbol=with_symbol)


def parse(text):
    return get_currency().parse(text)


def symbol():
    return get_currency().symbol()


def tax_term():
    return get_currency().tax_term()


def fmt_date(iso_date_str):
    return get_currency().fmt_date(iso_date_str)
