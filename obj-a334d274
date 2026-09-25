# UI Finalization and Orphaned Tasks Specification

## Objective 1: Theme Engine Expansion (Light Mode)
*   **Requirement:** The application currently defaults to a dark background. Implement a toggleable light/white theme option.
*   **Implementation:** 
    *   Expand the global CSS variables (or Tailwind configuration) to include a full light-mode color palette.
    *   Add a "Theme" toggle (Light/Dark/System) in the Settings tab.
    *   Ensure text contrast, border colors, and hover states adapt dynamically when the white background is active.

## Objective 2: Arabic Localization and RTL Layout Fixes
*   **Current State:** The English layout renders correctly[cite: 4]. However, switching to Arabic results in incomplete translations (e.g., sidebar category headers like "OPERATIONS" and "CLINICAL" remain in English) and improper structural mirroring[cite: 5].
*   **Implementation:**
    *   Ensure the `dir="rtl"` attribute is dynamically applied to the `<html>` or main `<body>` tag when Arabic (or any RTL language) is selected.
    *   Audit the i18n translation files to ensure 100% coverage for the sidebar, dashboard widgets, and settings menus. 
    *   Fix flexbox/grid alignments that break when the text direction flips from LTR to RTL.

## Objective 3: First-Run Welcome Window (Setup Wizard)
*   **Requirement:** Users must be greeted with a dedicated setup window on a fresh install before they can access the application.
*   **Implementation:** 
    *   Implement an initialization check on app boot. If the SQLite database (`pharmacy.db`) lacks an initial admin account or is newly created, the routing middleware MUST intercept the standard `/login` route.
    *   Redirect to a `/setup` or `/welcome` flow where the user is forced to input their initial pharmacy details, username, and password.

## Objective 4: Resolve Orphaned Tasks and Middleware Warnings
*   **Middleware Deprecation Warning:** Address the Next.js middleware deprecation warning noted in the ORPHANS list. 
    *   *Context:* This is likely a warning regarding outdated `NextRequest` header mutations or legacy `matcher` syntax in `middleware.ts`. While it may not break the current production build, it clutters the logs and risks breaking in future Next.js minor updates. 
    *   *Action:* Refactor `middleware.ts` to use the latest stable Next.js routing and request-handling API.
*   **ESLint Configuration:** Create the missing `eslint.config.mjs` file required for Next 16+ compatibility.
*   **Form Accessibility:** Complete the remaining `htmlFor` and `id` pairings for all `<label>` and `<input>` elements across the remaining dashboard forms to ensure full screen-reader and E2E automation compatibility.

## Objective 5: Manual Human Verification Protocol
The code work is complete. The only remaining item requires a human to run:

1. Delete or rename `%APPDATA%\PharmacySuite\pharmacy.db`
   (back it up first: copy it to Desktop)

2. Install the MSI at:
   `src-tauri\target\release\bundle\msi\Pharmacy Suite_1.0.0_x64_en-US.msi`

3. Open the installed app and confirm:
   - Setup wizard appears (not login screen)
   - Complete the wizard with a test username and password
   - Login with those credentials succeeds
   - All sidebar sections visible (Operations, Clinical, Insights, Tools, Administration)
   - Support tab shows pharmacypro.support@gmail.com
   - Bottom-left shows "Administrator" not "unknown"
   - Background is light/white not dark

4. After closing the app, run:
     `tasklist | findstr "backend"`
     `tasklist | findstr "node"`
   Confirm both return empty (no orphan sidecar processes)

5. Restore your original pharmacy.db from the backup

Report back with what you actually saw for each item. I will not accept "code says it should work" for the wizard — this must be visually confirmed by you running the installed MSI.