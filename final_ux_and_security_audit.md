# Final UX, Security, and Distribution Specification

## Objective 1: Universal Back-Navigation
*   **Requirement:** Users must never get stuck in deep views (e.g., viewing a specific patient, editing an invoice, or deep settings). 
*   **Implementation:** 
    *   Audit all nested routes in the React/Next.js frontend.
    *   Implement a global `Breadcrumb` or a consistent `<BackButton />` component at the top-left of the main content area for all sub-pages.
    *   Ensure the back button correctly pops the history stack (`router.back()`) without losing the parent view's state (e.g., keeping search filters intact when returning to the Inventory list).

## Objective 2: Remote Patch and Update Delivery Design
*   **Requirement:** Design a seamless, secure mechanism to deliver bug fixes and feature updates to users' installed desktop applications.
*   **Implementation:**
    *   Configure the native **Tauri Updater** (`tauri.conf.json` -> `updater`) to check a remote JSON endpoint for new versions.
    *   Design the secure update flow: the app must verify the Ed25519 signature of the downloaded patch before applying it to ensure the binary hasn't been tampered with.
    *   Create a strategy for database schema migrations during an update so that the local `pharmacy.db` is never corrupted when updating from v1.0.0 to v1.0.1.

## Objective 3: Anti-Phishing and Application Security Hardening
*   **Requirement:** Protect the application runtime and the official support email from interception, spoofing, and social engineering.
*   **Implementation - App Hardening:**
    *   Verify that the FastAPI sidecar strictly rejects any requests not originating from `127.0.0.1:3000` or the Tauri webview.
    *   Ensure the SQLite database file permissions are restricted strictly to the installing OS user profile.
*   **Implementation - Support Security:**
    *   Draft an official "Security Notice" to be embedded in the app's Support tab stating: *"Official support will NEVER ask for your password, your `secret.key` file, or your `pharmacy.db` file."*
    *   Configure DMARC, DKIM, and SPF records for the support email domain to prevent spoofed emails mimicking the developer.

## Objective 4: Microsoft Store Readiness Assessment
*   **Requirement:** Determine if the current architecture (Tauri + FastAPI sidecar + Node.js) has any blocking errors for the Microsoft Store Win32/UWP ecosystem.
*   **Implementation:**
    *   Review the codebase against the Windows App Certification Kit (WACK) requirements. 
    *   Ensure the FastAPI and Node.js sidecar processes properly terminate via Windows Job Objects when the main Tauri process is forcefully killed (preventing zombie processes, which causes Store rejection).
    *   Identify any required changes to package the application as an `.msix` instead of `.msi`, as MSIX is the native format for Microsoft Store distribution.