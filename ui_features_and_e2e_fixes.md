# UI Adjustments, Inventory Logic, and Backend Fixes

## Objective 1: UI Navigation and Theming Corrections
*   **Dark Theme Brightness:** The current dark background contrast is too deep[cite: 1]. Lighten the baseline background hex code slightly to reduce eye strain. 
*   **Settings Integration:** Add a "Brightness" or "Contrast" slider in the Settings tab that dynamically adjusts the CSS variables or UI theme parameters for the background layer.
*   **Dashboard Restoration:** Add a dedicated "Dashboard" or "Home" button at the very top of the left sidebar above "Point of Sale"[cite: 1] to serve as a permanent anchor.
*   **Back Button Implementation:** For deep views (e.g., viewing a specific patient or editing a specific invoice), implement a "Back" button at the top left of the main content area, or utilize a breadcrumb trail (e.g., `Inventory > Product Details > Edit`) to allow easy return to the parent tab.

## Objective 2: Advanced Inventory and Labeling Engine
*   **Inventory Tab Label Button:** Add a "Generate Label" action button to individual product rows in the Inventory tab. Clicking this should send the product context directly to the Label Engine.
*   **Bulk Import Labeling:** In the Bulk Import tab, add a toggle or column for "Generate Labels on Import." When active, the system should neatly queue labels for the imported batch.
*   **Barcode Generation Strategy:** Implement a robust barcode assignment system with two main categories:
    1.  **Manufacturer Barcode:** Use the existing product barcode if available.
    2.  **Pharmacy-Generated Barcode:** If the user opts to generate an internal barcode, provide the following options in the Label Engine/Inventory settings:
        *   *Random (Default/Safest):* Generate a unique, collision-resistant identifier (e.g., short UUID or cryptographically secure random string).
        *   *Sequential:* Auto-incrementing based on the database index (e.g., `10001`, `10002`).
        *   *Manual:* Allow the user to type a custom barcode.
        *   *Pattern-Based:* Allow the user to define a regex-style pattern (e.g., `RX-[YYYY]-[0000]`) that auto-fills based on the current date and item category.

## Objective 3: Backend Security and Logging (Spec 09 Part 1)
*   **Task A - JWT Security:** Modify the database initialization script. When a new database is freshly created (after an uninstall/wipe), the system MUST generate and rotate a new `secret.key`. This ensures old JWTs from previous installations cannot authenticate against the new instance.
*   **Task B - Rotating Logger:** Implement a rotating file logger for the backend. 
    *   File name: `backend.log`.
    *   Size limit: 5MB per file.
    *   Backup count: 3 (keep up to 3 old log files).
    *   Purpose: Allow buyers to easily retrieve and attach these logs to support emails.

## Objective 4: E2E Automation and State Management
*   **Task C - State Restoration:** Write a routine to restore the original `testadmin` database from the pre-MSI backup. Ensure the E2E test account is completely dropped so the machine returns exactly to its pre-test state.
*   **Task D - Clean-Room E2E Execution:** Create a master automation script that drives the entire application lifecycle with zero human intervention. The script must:
    1.  Uninstall the existing app.
    2.  Wipe all leftover application data/configs.
    3.  Install the new build.
    4.  Complete the setup wizard via UI automation.
    5.  Log in using test credentials.
    6.  Copy and export diagnostics to a designated folder.