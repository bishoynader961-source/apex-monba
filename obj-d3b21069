# App Repair & Roles/Permissions Feature — Execution Plan

**Purpose:** Hand this file to an AI coding agent (e.g. Claude Code) working directly in the app's codebase. It fixes broken UI first, then builds a full Users & Roles permission system with an admin "lock" mechanism, in a controlled, staged order so nothing breaks along the way.

**Ground rule for the agent:** Do NOT jump straight to code. Work section by section, in order. Within each section, complete every stage before moving to the next section. After each stage, run/verify the app before continuing. Do not touch Section 5 (Users & Roles) until Sections 1–4 are confirmed working — Section 5 is the most architecturally sensitive part and must be built last, on a stable base.

---

## Section 1 — Button Audit (fix first)

**Goal:** Every clickable button in the app does what it's supposed to do.

1. **Inventory** — Crawl every screen/component and list every button element, what it's supposed to do, and what it currently does (or fails to do).
2. **Reproduce** — For each button, click it in a running instance and record actual behavior (works / silent failure / console error / wrong action).
3. **Root-cause** — Group failures by cause (missing onClick handler, dead API endpoint, broken route, disabled state stuck on, etc.) rather than fixing one-by-one blindly.
4. **Fix** — Resolve each group, starting with the most common root cause.
5. **Verify** — Re-click every button from the inventory and confirm expected behavior. Produce a short checklist/report of button → status.

---

## Section 2 — Text Visibility / Font Color

**Goal:** Text is readable (black, or a sufficiently dark color) on every tab and background it appears on.

1. **Audit** — Scan every tab/page for text elements using a light/invisible font color on light backgrounds (the likely cause of "can't see text").
2. **Identify source** — Determine if this is a global CSS/theme variable issue (fix once, globally) or scattered inline styles (fix per-component). Prefer the global fix if possible.
3. **Apply fix** — Set default text color to black (or near-black, e.g. `#111`) across all tabs, preserving any intentional color coding (errors in red, links in blue, etc. — don't flatten everything to black).
4. **Verify** — Visually check every tab against a checklist to confirm all text is now visible.

---

## Section 3 — Tab Functionality Audit

**Goal:** Every tab loads and functions correctly. Example known issue: the **Analytics tab** throws an error (see attached screenshot) instead of loading.

1. **Inventory** — List every tab in the app.
2. **Reproduce** — Open each tab and record: loads fine / loads with errors / doesn't load at all. Capture exact error messages/stack traces (start with Analytics).
3. **Root-cause each broken tab** — Trace the error to its source (bad API call, missing data binding, broken route/component import, etc.).
4. **Fix** — Resolve tab by tab, starting with Analytics.
5. **Verify** — Reload every tab and confirm it renders and functions with no console errors.

---

## Section 4 — Label Engine Buttons

**Goal:** Every button inside the Label Engine works as intended, specifically including the **standalone button** and the **print button**.

1. **Inventory** — List every button inside the Label Engine module specifically.
2. **Reproduce** — Test each one, with particular focus on the standalone button and print button (call these out explicitly in the test log).
3. **Root-cause & fix** — Same pattern as Section 1, scoped to this module.
4. **Verify** — Confirm each Label Engine button performs its intended action, and that print output is correct.

---

## Section 5 — Users & Roles Permission System (build LAST, after Sections 1–4 pass)

**Goal:** A roles system where each role's access to tabs/functions is configurable, the app owner has full, unremovable access, and the owner can additionally password-lock specific features from being changed by anyone (including other admins), while being able to unlock/relock and add new lockable items over time — all without ever risking locking themselves out.

Work through these stages in order. Do not skip ahead.

### Stage 5.1 — Data Model Design (design only, no UI yet)
- Define entities: `User`, `Role`, `Permission` (maps a role to a tab/function it can access), and `LockedFeature` (a tab/button/function currently locked by the owner, with its own lock password hash).
- Decide the permission model: a simple allow-list per role (role → list of accessible tabs/functions) is enough; avoid over-engineering with complex inheritance.
- Write this data model down before writing any code, and confirm it against Stage 5.2 requirements below.

### Stage 5.2 — First-User-Is-Owner Bootstrap Logic
- The very first account created in the whole app (i.e., whoever purchases/installs and sets the initial name + password) is automatically created as `User { role_id: 1 }`.
- `role_id: 1` = **Owner/Admin**, hardcoded to have full access to every current and future tab/function. This role can never be demoted, deleted, or locked out by anyone, including by the lock feature in Stage 5.4.
- This bootstrap only fires once, on first account creation — not on every login.
- Explicitly test: create a fresh instance, confirm the first signup becomes role_id 1 automatically with full access and no manual role assignment needed.

### Stage 5.3 — Roles Tab: Permission Matrix
- Build the **Roles** tab: a list of roles, and for each role, a checklist of every tab/button/function in the app that can be toggled on/off for that role.
- Non-owner roles start with no access by default; the owner (or anyone the owner grants role-management rights to) checks the boxes for what each role can use.
- The owner can grant a role (or a specific user) full access equal to their own, if they choose to.
- This list must be extensible (see Stage 5.5) rather than a fixed hardcoded set — new tabs/buttons added to the app later should be addable here too.

### Stage 5.4 — Admin Lock Mechanism (separate from login password)
- Add a second, distinct password — the **lock password** — separate from any user's login password. Only role_id 1 (the owner) sets/knows/changes this.
- In the Roles tab, the owner can select any tab/button/function and toggle it **locked**. Once locked, no one (including other admins) can change that feature's settings/behavior without entering the lock password.
- Only role_id 1 is exempt from ever needing the lock password to make changes — everyone else, if they attempt to touch a locked item, is prompted for it.
- Specifically include **changing a user's login password** as one of the lockable functions: by default this should require the lock password to be changed by anyone other than the account owner changing their own password. Role_id 1 can always change their own login password freely, without ever needing the lock password, and can never be locked out of this.
- Locking is off by default for everything except this login-password-change rule, which is locked by default (owner's call to change that default later).

### Stage 5.5 — Extensible Lock/Permission Fields
- On the Roles tab, give the owner an "Add field" control so they can register additional tabs/buttons/functions into the permission matrix and lock list as the app grows, rather than being limited to a fixed set defined at build time.
- Support adding any number of these fields, and toggling each one locked/unlocked independently.
- (Optional, propose to the user before building) Consider whether some entries should be simple checkboxes (on/off access) vs. more granular options (e.g., "view only" vs "edit") — if you see a genuinely useful refinement here, propose it back before implementing rather than silently expanding scope.

### Stage 5.6 — Safety Rails
- Automated checks/tests confirming: role_id 1 can never be locked out, deleted, demoted, or blocked from changing their own login password.
- Confirm a fresh install → first signup → full-access owner flow works end-to-end with no manual database edits needed.

### Stage 5.7 — Final Verification (do this last, after Stages 5.1–5.6)
- Full walkthrough: create a second (non-owner) user, confirm they see only what their role permits, confirm locked items prompt for the lock password, confirm the owner can add a new field/lockable item live and it appears correctly, confirm owner's own login-password change never requires the lock password.

---

## Reporting format expected back after each Section

For Sections 1–4, a short table: item | before | after | verified (yes/no).
For Section 5, a short written summary per stage confirming what was built and what was tested, plus any refinement the AI wants to propose before continuing to the next stage.
