import os
import json
import tkinter as tk
from tkinter import ttk, messagebox
import customtkinter as ctk

LOCALES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "locales")
DEFAULT_LANGUAGE = "en"

SUPPORTED_LANGUAGES = {
    "en": "English",
    "es": "Español",
    "fr": "Français",
    "de": "Deutsch",
    "pt": "Português",
    "it": "Italiano",
}


class TranslationManager:
    """Manages multi-language translations for the application."""

    def __init__(self, config_loader=None):
        self.translations = {}
        self.current_lang = DEFAULT_LANGUAGE
        self.config_loader = config_loader
        self._load_all_translations()
        self._load_language_from_config()

    def _load_all_translations(self):
        """Load all available locale files from the locales directory."""
        if not os.path.exists(LOCALES_DIR):
            os.makedirs(LOCALES_DIR, exist_ok=True)
            return

        for filename in os.listdir(LOCALES_DIR):
            if filename.endswith(".json"):
                lang_code = filename[:-5]
                filepath = os.path.join(LOCALES_DIR, filename)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        self.translations[lang_code] = json.load(f)
                except (json.JSONDecodeError, IOError) as e:
                    print(f"[Translation] Failed to load {filename}: {e}")

    def _load_language_from_config(self):
        """Load the saved language preference from config.json."""
        if self.config_loader:
            try:
                config = self.config_loader()
                saved_lang = config.get("language", DEFAULT_LANGUAGE)
                if saved_lang in self.translations:
                    self.current_lang = saved_lang
            except Exception:
                pass

    def t(self, key, lang=None, **kwargs):
        """Translate a key to the current language.

        Args:
            key: The translation key (e.g., "save_button")
            lang: Optional language override
            **kwargs: Format placeholders (e.g., count=5 for "Imported {count} products")

        Returns:
            Translated string, or the key itself if not found
        """
        target_lang = lang or self.current_lang

        if target_lang not in self.translations:
            target_lang = DEFAULT_LANGUAGE

        translation = self.translations.get(target_lang, {}).get(key, key)

        if kwargs:
            try:
                translation = translation.format(**kwargs)
            except (KeyError, ValueError):
                pass

        return translation

    def set_language(self, lang_code):
        """Change the current language and persist to config."""
        if lang_code not in self.translations:
            lang_code = DEFAULT_LANGUAGE

        self.current_lang = lang_code

        if self.config_loader:
            try:
                import barcode_logic
                config = barcode_logic.load_config()
                config["language"] = lang_code
                config_path = barcode_logic.CONFIG_FILE
                with open(config_path, "w", encoding="utf-8") as f:
                    json.dump(config, f, indent=4, ensure_ascii=False)
            except Exception as e:
                print(f"[Translation] Failed to save language preference: {e}")

    def get_available_languages(self):
        """Returns list of available language codes."""
        return list(self.translations.keys())

    def get_language_display_name(self, lang_code):
        """Returns the display name for a language code."""
        return SUPPORTED_LANGUAGES.get(lang_code, lang_code)


# Global translation manager instance
_tm = None


def get_translation_manager():
    """Returns the global TranslationManager instance."""
    global _tm
    if _tm is None:
        _tm = TranslationManager()
    return _tm


def t(key, **kwargs):
    """Convenience function for translations."""
    return get_translation_manager().t(key, **kwargs)


class LanguageSelectorDialog(ctk.CTkToplevel):
    """First-run dialog for selecting the application language."""

    def __init__(self, parent=None, on_select=None):
        super().__init__(parent)
        self.title("Select Language / Seleccione Idioma / Choisir la Langue")
        self.geometry("380x300")
        self.resizable(False, False)
        self.grab_set()
        self.selected_language = None
        self.on_select = on_select

        self._build_ui()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self,
            text=t("choose_your_language"),
            font=ctk.CTkFont(size=18, weight="bold"),
        ).grid(row=0, column=0, padx=30, pady=(30, 20))

        self.lang_var = ctk.StringVar(value="en")

        languages = get_translation_manager().get_available_languages()
        for i, lang_code in enumerate(languages):
            display_name = get_translation_manager().get_language_display_name(lang_code)
            ctk.CTkRadioButton(
                self,
                text=display_name,
                variable=self.lang_var,
                value=lang_code,
                font=ctk.CTkFont(size=14),
            ).grid(row=i + 1, column=0, padx=30, pady=5, sticky="w")

        ctk.CTkButton(
            self,
            text=t("continue"),
            command=self._confirm,
            height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=len(languages) + 2, column=0, padx=30, pady=(20, 30), sticky="ew")

    def _confirm(self):
        self.selected_language = self.lang_var.get()
        if self.on_select:
            self.on_select(self.selected_language)
        self.destroy()


def check_first_run_language(parent=None, on_language_set=None):
    """Shows the language selector if no language preference is saved.

    Args:
        parent: Parent window for the dialog
        on_language_set: Callback called with the selected language code

    Returns:
        True if language was selected, False if already configured
    """
    import barcode_logic
    config = barcode_logic.load_config()

    if "language" in config:
        return False

    def on_select(lang_code):
        tm = get_translation_manager()
        tm.set_language(lang_code)
        if on_language_set:
            on_language_set(lang_code)

    dialog = LanguageSelectorDialog(parent, on_select=on_select)
    dialog.wait_window()
    return True
