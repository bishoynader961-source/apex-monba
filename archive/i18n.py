"""
i18n.py — Internationalization module for PharmacyPro desktop app.

Provides:
    - load_translations(): Load all locale JSON files
    - t(key, **kwargs): Get translated string with optional format args
    - set_language(lang_code): Switch language and persist preference
    - get_language(): Return current active language code
    - get_available_languages(): Return list of (code, name) tuples
    - on_language_change(callback): Register a callback for language switches
"""
import json
import os
from pathlib import Path

_LOCALES_DIR = Path(__file__).resolve().parent / "locales"
_PREF_FILE = Path.home() / ".pharmacy_lang"
_TRANSLATIONS: dict[str, dict[str, str]] = {}
_CURRENT_LANG: str = "en"
_LISTENERS: list = []

_FALLBACK_LANG = "en"
_LANG_DISPLAY_NAMES = {
    "en": "English",
    "ar": "العربية",
    "de": "Deutsch",
    "es": "Español",
    "fr": "Français",
    "pt": "Português",
}


def load_translations() -> None:
    """Discover and load all JSON files from the locales/ directory."""
    global _TRANSLATIONS
    if not _LOCALES_DIR.is_dir():
        return
    for json_file in sorted(_LOCALES_DIR.glob("*.json")):
        lang_code = json_file.stem
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                _TRANSLATIONS[lang_code] = data
        except (json.JSONDecodeError, OSError):
            continue


def get_available_languages() -> list[tuple[str, str]]:
    """Return [(code, display_name), ...] for all loaded locales."""
    result = []
    for code in sorted(_TRANSLATIONS.keys()):
        name = _LANG_DISPLAY_NAMES.get(code, code.upper())
        result.append((code, name))
    return result


def get_language() -> str:
    """Return the current active language code."""
    return _CURRENT_LANG


def set_language(lang_code: str) -> bool:
    """Switch the active language. Returns True if the language was loaded."""
    global _CURRENT_LANG
    if lang_code not in _TRANSLATIONS:
        return False
    _CURRENT_LANG = lang_code
    _save_preference(lang_code)
    for cb in _LISTENERS:
        try:
            cb(lang_code)
        except Exception:
            pass
    return True


def t(key: str, **kwargs) -> str:
    """Translate a key, with optional {placeholder} interpolation.

    Falls back to the English translation, then to the raw key itself.
    """
    value = _TRANSLATIONS.get(_CURRENT_LANG, {}).get(key)
    if value is None:
        value = _TRANSLATIONS.get(_FALLBACK_LANG, {}).get(key)
    if value is None:
        value = key
    if kwargs:
        try:
            value = value.format(**kwargs)
        except (KeyError, IndexError):
            pass
    return value


def on_language_change(callback) -> None:
    """Register a callable to be invoked when the language switches."""
    _LISTENERS.append(callback)


def unregister_listener(callback) -> None:
    """Remove a previously registered language-change listener by identity.

    Prevents leaked closures from accumulating in ``_LISTENERS`` after a widget
    is destroyed (the i18n listener list is never pruned automatically).
    Removing during a ``set_language`` broadcast is safe because that loop
    iterates a snapshot of ``_LISTENERS``.
    """
    global _LISTENERS
    _LISTENERS = [cb for cb in _LISTENERS if cb is not callback]


def _save_preference(lang_code: str) -> None:
    """Persist the language choice to ~/.pharmacy_lang."""
    try:
        _PREF_FILE.write_text(lang_code, encoding="utf-8")
    except OSError:
        pass


def _load_preference() -> str:
    """Read the persisted language preference, defaulting to 'en'."""
    try:
        code = _PREF_FILE.read_text(encoding="utf-8").strip()
        if code in _TRANSLATIONS:
            return code
    except OSError:
        pass
    return "en"


def init() -> None:
    """One-call initializer: load locales, restore saved language."""
    load_translations()
    global _CURRENT_LANG
    _CURRENT_LANG = _load_preference()
