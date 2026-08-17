"""
quick_sig.py — Quick-SIG template system for PharmacyPro.

Provides:
  - save_quick_sig_template(name, fields_dict): Persist a SIG template
  - load_quick_sig_templates(favorites_only=False): Load templates from DB
  - delete_quick_sig_template(template_id): Remove a template
  - get_sig_suggestions(query, limit=10): Fuzzy search templates
  - QuickSigBuilder: UI component (CTkFrame) for building/editing SIG templates
    with dose, route, frequency, duration, and directions fields. Drag-from-suggestions
    to build composite directions.

Integrates with:
  - database (quick_sig_templates table)
  - i18n (t() for labels)
  - customtkinter.CTkFrame
"""
import os
import sqlite3
import logging
from datetime import datetime
from functools import partial

import customtkinter as ctk

import i18n
from path_utils import get_resource_path

try:
    from db import get_db_path, SessionLocal, QuickSigTemplate
    _USE_SQLA = True
except ImportError:
    _USE_SQLA = False
    from database import get_db_path

try:
    import native_accel
    _HAS_NATIVE_ACCEL = True
except ImportError:
    native_accel = None
    _HAS_NATIVE_ACCEL = False

log = logging.getLogger("quick_sig")

_TABLE_CHECK = """
SELECT name FROM sqlite_master WHERE type='table' AND name='quick_sig_templates'
"""


def _ensure_table(conn: sqlite3.Connection):
    """Ensure quick_sig_templates exists on raw sqlite connection (used for fallback path)."""
    if conn.execute(_TABLE_CHECK).fetchone() is None:
        conn.execute("""
            CREATE TABLE quick_sig_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                drug_name TEXT DEFAULT '',
                dose TEXT DEFAULT '',
                route TEXT DEFAULT '',
                frequency TEXT DEFAULT '',
                duration TEXT DEFAULT '',
                directions TEXT DEFAULT '',
                is_favorite INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            )
        """)
        conn.commit()


def save_quick_sig_template(
    name: str,
    drug_name: str = "",
    dose: str = "",
    route: str = "",
    frequency: str = "",
    duration: str = "",
    directions: str = "",
    is_favorite: int = 0,
) -> int:
    """Save a Quick-SIG template. Returns the template ID.

    If a template with the same name exists, it is updated (upsert-like by name).
    """
    if not name:
        name = "Untitled"
    created_at = datetime.now().isoformat()
    if _USE_SQLA and SessionLocal is not None:
        try:
            with SessionLocal() as session:
                existing = session.query(QuickSigTemplate).filter_by(name=name).first()
                if existing:
                    existing.drug_name = drug_name
                    existing.dose = dose
                    existing.route = route
                    existing.frequency = frequency
                    existing.duration = duration
                    existing.directions = directions
                    existing.is_favorite = is_favorite
                    existing.created_at = created_at
                    template_id = existing.id
                else:
                    tpl = QuickSigTemplate(
                        name=name, drug_name=drug_name, dose=dose, route=route,
                        frequency=frequency, duration=duration, directions=directions,
                        is_favorite=is_favorite, created_at=created_at,
                    )
                    session.add(tpl)
                    session.commit()
                    template_id = tpl.id
                return template_id
        except Exception as e:
            log.error("save_quick_sig_template (SQLAlchemy) failed: %s", e)

    conn = sqlite3.connect(get_db_path())
    _ensure_table(conn)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM quick_sig_templates WHERE name = ?", (name,))
    row = cursor.fetchone()
    if row:
        cursor.execute(
            "UPDATE quick_sig_templates SET drug_name=?, dose=?, route=?, frequency=?, "
            "duration=?, directions=?, is_favorite=?, created_at=? WHERE id=?",
            (drug_name, dose, route, frequency, duration, directions, is_favorite, created_at, row[0]),
        )
        template_id = row[0]
    else:
        cursor.execute(
            "INSERT INTO quick_sig_templates (name, drug_name, dose, route, frequency, "
            "duration, directions, is_favorite, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (name, drug_name, dose, route, frequency, duration, directions, is_favorite, created_at),
        )
        template_id = cursor.lastrowid
    conn.commit()
    conn.close()
    log.info("Saved Quick-SIG template: '%s' (id=%d)", name, template_id)
    return template_id


def load_quick_sig_templates(favorites_only: bool = False) -> list[dict]:
    """Load all (or favorite-only) Quick-SIG templates from the DB.

    Returns list of dicts with keys: id, name, drug_name, dose, route,
    frequency, duration, directions, is_favorite, created_at.
    """
    if _USE_SQLA and SessionLocal is not None:
        try:
            with SessionLocal() as session:
                query = session.query(QuickSigTemplate)
                if favorites_only:
                    query = query.filter(QuickSigTemplate.is_favorite == 1)
                query = query.order_by(
                    QuickSigTemplate.is_favorite.desc(),
                    QuickSigTemplate.created_at.desc(),
                )
                return [
                    {
                        "id": t.id, "name": t.name, "drug_name": t.drug_name,
                        "dose": t.dose, "route": t.route, "frequency": t.frequency,
                        "duration": t.duration, "directions": t.directions,
                        "is_favorite": t.is_favorite, "created_at": t.created_at,
                    }
                    for t in query.all()
                ]
        except Exception as e:
            log.error("load_quick_sig_templates (SQLAlchemy) failed: %s", e)

    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    _ensure_table(conn)
    sql = "SELECT * FROM quick_sig_templates"
    if favorites_only:
        sql += " WHERE is_favorite = 1"
    sql += " ORDER BY is_favorite DESC, created_at DESC"
    rows = conn.execute(sql).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_quick_sig_template(template_id: int) -> bool:
    """Delete a Quick-SIG template by ID. Returns True if a row was deleted."""
    if _USE_SQLA and SessionLocal is not None:
        try:
            with SessionLocal() as session:
                tpl = session.get(QuickSigTemplate, template_id)
                if tpl:
                    session.delete(tpl)
                    session.commit()
                    return True
                return False
        except Exception as e:
            log.error("delete_quick_sig_template (SQLAlchemy) failed: %s", e)

    conn = sqlite3.connect(get_db_path())
    _ensure_table(conn)
    cursor = conn.execute("DELETE FROM quick_sig_templates WHERE id = ?", (template_id,))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    if deleted:
        log.info("Deleted Quick-SIG template id=%d", template_id)
    return deleted > 0


def toggle_favorite(template_id: int) -> int | None:
    """Toggle the is_favorite flag for a template. Returns the new value, or None if not found."""
    conn = sqlite3.connect(get_db_path())
    _ensure_table(conn)
    cursor = conn.execute(
        "UPDATE quick_sig_templates SET is_favorite = 1 - is_favorite WHERE id = ?", (template_id,)
    )
    conn.commit()
    new_val = None
    if cursor.rowcount:
        new_val = conn.execute(
            "SELECT is_favorite FROM quick_sig_templates WHERE id = ?", (template_id,)
        ).fetchone()
        if new_val:
            new_val = new_val[0]
    conn.close()
    return new_val


def get_sig_suggestions(query: str, limit: int = 10) -> list[dict]:
    """Fuzzy-search Quick-SIG templates by name, drug_name, or directions.

    Uses rapidfuzz (via native_accel) for typo-tolerant ranking when available,
    falling back to SQL LIKE search with a Python-side fuzzy fallback.
    """
    if not query:
        return load_quick_sig_templates(favorites_only=True)
    like = f"%{query}%"
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    _ensure_table(conn)
    rows = conn.execute(
        "SELECT * FROM quick_sig_templates "
        "WHERE name LIKE ? OR drug_name LIKE ? OR directions LIKE ? OR frequency LIKE ? "
        "ORDER BY is_favorite DESC, created_at DESC LIMIT ?",
        (like, like, like, like, limit * 3),
    ).fetchall()
    conn.close()
    templates = [dict(r) for r in rows]
    if not _HAS_NATIVE_ACCEL or not templates:
        return templates[:limit]
    template_names = [t.get("name", "") for t in templates]
    ranked = native_accel.fuzzy_search(query, template_names, limit=limit, cutoff=65, scorer="partial")
    if ranked:
        return [templates[idx] for _name, _score, idx in ranked]
    return templates[:limit]


# ── Pre-defined common SIG components for the suggestion palette ──────────

COMMON_DOSES = ["0.5 mg", "1 mg", "2.5 mg", "5 mg", "10 mg", "25 mg", "50 mg", "100 mg",
                 "0.5 mL", "1 mL", "2.5 mL", "5 mL", "10 mL", "1 tab", "2 tabs", "1 cap",
                 "1 drop", "0.1 mg", "0.25 mg", "100 mcg", "200 mcg", "400 IU"]

COMMON_ROUTES = ["by mouth", "sublingual", "topical", "eye drops", "ear drops",
                 "nose drops", "inhalation", "intramuscular", "subcutaneous",
                 "transdermal", "vaginal", "rectal"]

COMMON_FREQS = ["QD", "BID", "TID", "QID", "QHS", "QAM", "QPM", "QOD", "QWK",
                "AC", "PC", "hs", "q2h", "q4h", "q6h", "q8h", "q12h",
                "tid", "qid", "once", "prn"]

COMMON_DURATIONS = ["3 days", "5 days", "7 days", "10 days", "14 days", "30 days",
                     "7 days", "90 days", "as needed", "1 week", "2 weeks", "1 month"]


class QuickSigBuilder(ctk.CTkFrame):
    """UI component for building, saving, and loading Quick-SIG prescription directions.

    Fields: drug_name, dose, route, frequency, duration, directions, is_favorite
    """

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.template_id: int | None = None
        self._build_ui()

    def _build_ui(self):
        self.grid_columnconfigure(1, weight=1)

        # ── Field rows ──
        fields = [
            ("quick_sig_name", "Name"),
            ("quick_sig_drug", "Drug"),
            ("quick_sig_dose", "Dose"),
            ("quick_sig_route", "Route"),
            ("quick_sig_frequency", "Frequency"),
            ("quick_sig_duration", "Duration"),
            ("quick_sig_directions", "Directions"),
        ]

        self._entries: dict[str, ctk.CTkEntry] = {}
        self._labels: dict[str, ctk.CTkLabel] = {}

        for i, (key, fallback) in enumerate(fields):
            label = ctk.CTkLabel(self, text=i18n.t(key))
            label.grid(row=i, column=0, sticky="e", padx=(10, 5), pady=4)
            self._labels[key] = label

            entry = ctk.CTkEntry(self, placeholder_text=i18n.t(key))
            entry.grid(row=i, column=1, sticky="ew", padx=(5, 5), pady=4)
            self._entries[key] = entry

        # Favorite toggle
        self._fav_var = ctk.BooleanVar(value=False)
        fav_check = ctk.CTkCheckBox(
            self, text=i18n.t("quick_sig_favorite"), variable=self._fav_var
        )
        fav_check.grid(row=len(fields), column=0, sticky="w", padx=10, pady=4)

        # ── Suggestion palette (dose, route, freq, duration) ──
        palette_frame = ctk.CTkFrame(self, fg_color="transparent")
        palette_frame.grid(row=len(fields) + 1, column=0, columnspan=2, sticky="ew", padx=10, pady=(10, 5))
        palette_frame.grid_columnconfigure(0, weight=1)

        palette_title = ctk.CTkLabel(
            palette_frame, text=i18n.t("quick_sig_suggestions"),
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        palette_title.grid(row=0, column=0, sticky="w")

        self._palette_container = ctk.CTkScrollableFrame(palette_frame, height=120)
        self._palette_container.grid(row=1, column=0, sticky="nsew", pady=5)
        self._palette_container.grid_columnconfigure(0, weight=1)

        self._populate_palette()

        # ── Action buttons ──
        button_row = len(fields) + 2
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=button_row, column=0, columnspan=2, sticky="ew", padx=10, pady=10)

        save_btn = ctk.CTkButton(btn_frame, text=i18n.t("save"), width=100)
        save_btn.pack(side="left", padx=(0, 5))
        save_btn.bind("<Button-1>", self._on_save, add="+")

        clear_btn = ctk.CTkButton(btn_frame, text=i18n.t("clear"), width=100)
        clear_btn.pack(side="left", padx=5)
        clear_btn.bind("<Button-1>", self._on_clear, add="+")

        fav_btn = ctk.CTkButton(btn_frame, text=i18n.t("quick_sig_toggle_favorite"), width=120)
        fav_btn.pack(side="left", padx=5)
        fav_btn.bind("<Button-1>", self._on_toggle_favorite, add="+")

    def _populate_palette(self):
        """Create clickable suggestion chips for common SIG components."""
        categories = [
            (i18n.t("quick_sig_dose_label"), COMMON_DOSES),
            (i18n.t("quick_sig_route_label"), COMMON_ROUTES),
            (i18n.t("quick_sig_frequency_label"), COMMON_FREQS),
            (i18n.t("quick_sig_duration_label"), COMMON_DURATIONS),
        ]

        for cat_title, items in categories:
            cat_label = ctk.CTkLabel(
                self._palette_container, text=cat_title,
                font=ctk.CTkFont(size=10, weight="bold"),
            )
            cat_label.pack(anchor="w", padx=5, pady=(8, 2))

            row_frame = ctk.CTkFrame(self._palette_container, fg_color="transparent")
            row_frame.pack(fill="x", padx=5, pady=2)

            for item in items:
                btn = ctk.CTkButton(
                    row_frame, text=item, width=90, height=24,
                    command=partial(self._insert_suggestion, item),
                )
                btn.pack(side="left", padx=2, pady=1)

    def _insert_suggestion(self, text: str):
        """Insert a suggestion into the directions field at cursor, or the most relevant field."""
        directions_entry = self._entries["quick_sig_directions"]
        current = directions_entry.get()
        if not current:
            directions_entry.insert(0, text)
        else:
            directions_entry.insert(len(current), f" {text}")
        directions_entry.focus_set()

    def _on_save(self, event=None):
        """Save the current form to the database."""
        name = self._entries["quick_sig_name"].get()
        template_id = save_quick_sig_template(
            name=name or "Untitled",
            drug_name=self._entries["quick_sig_drug"].get(),
            dose=self._entries["quick_sig_dose"].get(),
            route=self._entries["quick_sig_route"].get(),
            frequency=self._entries["quick_sig_frequency"].get(),
            duration=self._entries["quick_sig_duration"].get(),
            directions=self._entries["quick_sig_directions"].get(),
            is_favorite=1 if self._fav_var.get() else 0,
        )
        self.template_id = template_id
        log.info("Quick-SIG template saved: id=%d name='%s'", template_id, name)

    def _on_clear(self, event=None):
        """Clear all form fields."""
        for entry in self._entries.values():
            entry.delete(0, "end")
        self._fav_var.set(False)
        self.template_id = None

    def _on_toggle_favorite(self, event=None):
        """Toggle favorite status of the currently loaded/saved template."""
        if self.template_id is None:
            return
        new_val = toggle_favorite(self.template_id)
        self._fav_var.set(bool(new_val))
        log.info("Toggled favorite for template id=%d -> %s", self.template_id, bool(new_val))

    def load_template(self, template: dict):
        """Load a template dict into the form fields."""
        self._entries["quick_sig_name"].delete(0, "end")
        self._entries["quick_sig_name"].insert(0, template.get("name", ""))
        self._entries["quick_sig_drug"].delete(0, "end")
        self._entries["quick_sig_drug"].insert(0, template.get("drug_name", ""))
        self._entries["quick_sig_dose"].delete(0, "end")
        self._entries["quick_sig_dose"].insert(0, template.get("dose", ""))
        self._entries["quick_sig_route"].delete(0, "end")
        self._entries["quick_sig_route"].insert(0, template.get("route", ""))
        self._entries["quick_sig_frequency"].delete(0, "end")
        self._entries["quick_sig_frequency"].insert(0, template.get("frequency", ""))
        self._entries["quick_sig_duration"].delete(0, "end")
        self._entries["quick_sig_duration"].insert(0, template.get("duration", ""))
        self._entries["quick_sig_directions"].delete(0, "end")
        self._entries["quick_sig_directions"].insert(0, template.get("directions", ""))
        self._fav_var.set(bool(template.get("is_favorite", 0)))
        self.template_id = template.get("id")

    def get_template_data(self) -> dict:
        """Return current form data as a dict."""
        return {
            "name": self._entries["quick_sig_name"].get(),
            "drug_name": self._entries["quick_sig_drug"].get(),
            "dose": self._entries["quick_sig_dose"].get(),
            "route": self._entries["quick_sig_route"].get(),
            "frequency": self._entries["quick_sig_frequency"].get(),
            "duration": self._entries["quick_sig_duration"].get(),
            "directions": self._entries["quick_sig_directions"].get(),
            "is_favorite": 1 if self._fav_var.get() else 0,
        }


def setup_quick_sig_tab(self, parent=None):
    """Tab-setup function attached to PharmacyApp via monkey-patching."""
    if parent is None:
        parent = self.tab_quick_sig

    frame = QuickSigBuilder(parent, fg_color="transparent")
    frame.pack(fill="both", expand=True, padx=4, pady=4)

    # Store references for refresh
    self.quick_sig_builder = frame
    self.quick_sig_frame = frame

    def _refresh(self):
        pass

    self._refresh_quick_sig_tab = _refresh
    return frame
