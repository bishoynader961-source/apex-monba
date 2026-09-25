# Pharmacy Suite Comprehensive Refactoring and RBAC Master Specification

## Stage 1: Global UI Interactivity and Visibility Audit

* **Button Functionality Verification:** Audit and test every interactive button across all operational modules (POS, Inventory, Expiry Alerts, and Administration,etc..) to ensure complete operational reliability without silent failures.
* **Global Typography Contrast Enforcement:** Force font colors across all tabs, data grids, tables, and modal containers to solid black to guarantee high legibility and resolve visibility issues where text blends into backgrounds.
* **Component Stability Checks:** Verify that every primary view and navigation link renders correctly and responds instantly to user inputs.

## Stage 2: Analytics Module Error Patching

* **Exception Identification:** Address the specific runtime crash occurring in the Analytics tab caused by unhandled empty array reductions.
* **Safe Array Reduction Implementation:** Patch all `.reduce()` operations across analytics and reporting scripts by supplying explicit initial fallback values to prevent abrupt application crashes when datasets are empty.
* **Data Validation Checks:** Ensure all numerical aggregation pipelines handle null, undefined, or empty data gracefully with proper UI fallback states.

## Stage 3: Label Engine Complete Feature Activation

* **Standalone Window Integration:** Wire the Open Standalone button to launch a dedicated secondary webview window for label design without disrupting the main application workflow.
* **Native Print Pipeline:** Connect the Print button to execute native operating system print dialogues and device routines via Tauri IPC backend commands.
* **Template Serialization:** Fully activate template saving, loading, naming, product ID linking, and export features to ensure seamless user management of label assets.

## Stage 4: Immutable Administrator Provisioning and Seeding

* **First-Launch Seeding Process:** Implement an automated boot sequence that detects if the user database is empty upon initial installation or purchase.
* **Automatic Admin Creation:** Automatically assign the first creator/purchaser as User ID 1 and link them to Role ID 1 (Administrator) with full, unrestricted permissions.
* **Backend Security Guards:** Hardcode robust backend safety checks preventing the deletion of User ID 1 or the modification of Role ID 1 permissions under any circumstance.

## Stage 5: Advanced Granular RBAC, Dynamic Locking, and Secure Re-Authentication

* **Granular Role Configuration:** Refine the Users and Roles tabs as the final step to allow granular permission assignments, letting administrators select exactly which tabs, sections, or individual buttons can be accessed by specific user accounts.
* **Dynamic Custom Permission Fields:** Enable administrators to add arbitrary new fields, buttons, or custom tabs dynamically into the permission matrix to accommodate future workflow expansions.
* **Secure Re-Authentication Mechanism:** Implement a secondary password confirmation prompt for high-privilege actions (such as changing login passwords, modifying roles, deleting users, or managing system locks). This must secure sensitive actions without accidentally logging out the active administrator.
* **Admin Privilege Bypass:** Ensure the primary administrator with Role ID 1 automatically bypasses all functional locks and custom restrictions.
* **Structured Multi-Stage Execution:** Guide the AI through independent, sequential phases to implement these architecture designs cleanly without disrupting the existing offline-first Tauri and SQLite framework.