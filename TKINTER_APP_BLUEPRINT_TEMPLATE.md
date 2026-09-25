# CustomTkinter App - Master Architecture & Refinement Blueprint

## 1. System Overview
*   **UI Framework:** CustomTkinter / Tkinter (Python 3.x)
*   **Database:** SQLite 3 (via `sqlite3` or SQLAlchemy ORM)
*   **Threading Strategy:** `threading.Thread` or `concurrent.futures` with `root.after()` callbacks for UI updates
*   **Packaging Target:** PyInstaller Spec -> MSIX Installer

## 2. Codebase Map
*(AI Agent: Map out the existing python codebase below)*
*   **Main Window & Navigation:** (e.g., `main.py`, `gui/app.py`, sidebar/tab switching logic)
*   **Database Layer:** (e.g., `database/db_manager.py`, connection pooling, schema initialization)
*   **UI Views & Controllers:**
    *   POS / Main Feature Frame:
    *   Inventory / Data Management:
    *   Settings & Configurations:
    *   Licensing / Activation Dialogs:

## 3. Tkinter Quality & Stability Checklist
1.  **Thread Safety:** Long-running database or network operations must NOT run on the main Tkinter thread. All background thread completion handlers MUST interact with UI widgets using `root.after()` or queue polling.
2.  **Explicit Asset Paths:** All image, icon, and custom theme `.json` files must be loaded using relative runtime path resolvers (`sys._MEIPASS` compatible for PyInstaller execution).
3.  **Exception Handling:** Wrap all GUI button callbacks with a global exception catcher (`tkinter.Tk.report_callback_exception`) that displays user-friendly error popups (`CTkMessagebox`) instead of silently crashing in the console.
4.  **DPI Scaling:** Verify `customtkinter.set_widget_scaling()` and window geometry settings render cleanly across multiple screen resolutions.