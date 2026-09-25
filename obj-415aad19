# App Diagnostics and Improvement Specification

## Phase 1: Comprehensive System Diagnostic
Perform a deep scan of the current codebase to identify and resolve underlying issues before adding new features.
*   **Static Analysis & Linting:** Run static analysis to identify unused variables, dead code, and typing inconsistencies across the frontend and backend.
*   **Dependency Audit:** Check for outdated packages or security vulnerabilities in current dependencies. Update to stable versions where necessary.
*   **State Management Check:** Analyze how state is passed between UI components. Identify any prop-drilling or redundant state updates causing unnecessary re-renders.
*   **Accessibility & Form Linking:** Scan all form `<label>` elements (especially in the login and setup wizard) and ensure they are programmatically linked to their inputs using `htmlFor` and `id` attributes to resolve Playwright/screen-reader matching failures.
*   **Database Integrity:** Verify SQLite database connections. Ensure connection pooling is optimized and that there are no unclosed cursors or unhandled transaction rollbacks leading to database locks.

## Phase 2: Remediation of Identified Problems
*   **Fix UI Blocking:** Ensure all heavy backend calls, database queries, or external API requests are strictly asynchronous and do not block the main UI thread.
*   **Error Handling:** Standardize error boundaries in the UI. Ensure backend exceptions are caught and translated into user-friendly toast notifications rather than raw stack traces.
*   **Memory Leak Prevention:** Audit components that subscribe to events or background processes. Ensure cleanup functions are properly defined when components unmount.

## Phase 3: General App Improvements
*   **Caching Strategy:** Implement memory caching for highly queried, infrequently changed data (e.g., Settings, Categories, Roles) to reduce database overhead.
*   **Input Validation:** Strengthen frontend and backend input validation. Ensure all text inputs sanitize data to prevent injection attacks and enforce character limits.
*   **Responsive Refinements:** Adjust padding, margins, and flex/grid layouts to ensure the application scales smoothly if the window is resized.
*   **Performance:** Implement lazy loading for tabs and heavy modules (like Analytics or Reporting) so they only load into memory when clicked.