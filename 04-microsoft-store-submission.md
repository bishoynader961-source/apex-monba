# SPEC 04 — Microsoft Store Submission Guide

**Architecture reference:** APP_BLUEPRINT.md Section 5 (Microsoft Store Readiness Checklist), `src-tauri/tauri.conf.json`

**Important:** Apply Spec 01 and Spec 02 before starting this spec. The store submission requires a clean, releasable build.

---

## Step 1 — Understand the Format Gap (NSIS vs MSIX)

Your current build produces an NSIS installer (`.exe`). Microsoft Store requires MSIX format. These are completely different packaging formats.

**What this means practically:**
- You cannot submit your current `.exe` installer directly to the Microsoft Store
- You must either: (a) convert to MSIX, or (b) package your NSIS app inside an MSIX wrapper
- Tauri supports MSIX generation — it's a config change plus additional tooling

**Decision point:** The easiest path for Tauri apps is to use the [MSIX Packaging Tool](https://learn.microsoft.com/en-us/windows/msix/packaging-tool/tool-overview) to wrap your existing NSIS installer. This is faster than reconfiguring Tauri for native MSIX output and produces a Store-compatible package. However, native Tauri MSIX is cleaner long-term.

---

## Step 2 — Get a Microsoft Partner Center Account

1. Go to [partner.microsoft.com](https://partner.microsoft.com) and click "Join now"
2. Sign in with a Microsoft account (or create one)
3. Select "App developer" as your account type
4. Choose Individual ($19 one-time registration fee) or Company account
5. Complete identity verification (takes 1–5 business days for company accounts)
6. Once approved, you can access the Partner Center dashboard

---

## Step 3 — Code Signing Certificate (Required)

The Microsoft Store requires your app to be signed. There are two scenarios:

**Scenario A: Submit through the Store (easier)**
Microsoft signs your app automatically when you submit through Partner Center. You only need to sign your MSIX package locally for testing — you can use a self-signed cert for that.

**Scenario B: Side-loaded distribution (outside Store)**
Requires an EV (Extended Validation) code signing certificate from a trusted CA (DigiCert, Sectigo, etc.). EV certs cost $200–400/year and require identity verification.

**For Store submission: Scenario A is the right path.** You don't need to buy a cert right now.

---

## Step 4 — Build the MSIX Package

### Option A: Wrap existing NSIS with MSIX Packaging Tool (fastest)

1. Install [MSIX Packaging Tool](https://apps.microsoft.com/detail/9n5lw3jbcxkf) from the Microsoft Store on your Windows machine
2. Open the tool and select "Application package"
3. Select "Create package on this computer"
4. Point it to your NSIS `.exe` installer
5. Fill in the package identity:
   - Name: `PharmacySuite` (matches `identifier` in `tauri.conf.json`)
   - Publisher: `CN=YourCompanyName` (must match your Partner Center publisher ID)
   - Version: `1.0.0.0` (MSIX requires 4-part version)
6. Install your app in the monitored environment
7. Let the tool capture the installation
8. Save the resulting `.msix` file

### Option B: Native Tauri MSIX (cleaner, more work)

In `src-tauri/tauri.conf.json`, under `bundle`:
```json
{
  "bundle": {
    "targets": ["nsis", "msi"],
    "windows": {
      "certificateThumbprint": null,
      "digestAlgorithm": "sha256",
      "timestampUrl": ""
    }
  }
}
```

Then run:
```
npm run tauri build -- --bundles msi
```

The `.msi` can be converted to `.msix` using `MakeAppx.exe` from the Windows SDK.

---

## Step 5 — App Identity Configuration

In `src-tauri/tauri.conf.json`, set the correct identifiers:
```json
{
  "identifier": "com.pharmacysuite.app",
  "productName": "Pharmacy Suite",
  "version": "1.0.0"
}
```

In Partner Center when you reserve your app name, you'll get a Package Identity that looks like:
```
Name: 12345YourCompany.PharmacySuite
Publisher: CN=XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX
```
These values must match what's in your MSIX manifest exactly.

---

## Step 6 — Privacy Policy (Required)

The Microsoft Store requires a privacy policy URL for any app that handles personal data. Pharmacy Suite handles patient records, so this is mandatory.

**What your privacy policy must cover:**
- What data the app collects (patient names, prescriptions, payment info)
- Where data is stored (local SQLite database on the user's machine)
- Whether data is transmitted to external servers (it isn't, beyond the license service)
- How users can delete their data
- Contact information for privacy questions

**Create a simple privacy policy:**
1. Write a privacy policy document (use a template from [privacypolicytemplate.net](https://www.privacypolicytemplate.net))
2. Host it on a public URL — cheapest option is a free GitHub Pages site:
   - Create a public GitHub repo named `pharmacysuite-privacy`
   - Add a `privacy.md` file with your policy
   - Enable GitHub Pages
   - Your URL: `https://yourusername.github.io/pharmacysuite-privacy`
3. Add this URL to your Partner Center submission

---

## Step 7 — Age Rating

In Partner Center, complete the age rating questionnaire. For a pharmacy management app:
- Select "Business & Productivity" category
- Age rating will likely be "Everyone" or "3+" — no mature content
- Answer "No" to all questions about violence, sexual content, etc.

---

## Step 8 — App Icons and Store Listing Assets

**Required for Store listing:**
- Store logo: 300x300 PNG (your app icon)
- Key art: 1920x1080 PNG (promotional banner showing the app)
- Screenshots: at least 1, max 10 (1366x768 minimum, 16:9 recommended)
- App description: 10,000 characters max
- Short description: 100 characters max
- App category: Business > Finance (or Productivity > Business)

**Take screenshots showing:**
1. Dashboard with all sections
2. POS in use
3. Inventory management
4. Patient records
5. Label Engine

---

## Step 9 — Partner Center Submission

1. Log into [partner.microsoft.com/dashboard](https://partner.microsoft.com/dashboard)
2. Click "Create a new app" → reserve your app name "Pharmacy Suite"
3. Click "Start a submission"
4. Complete all sections:
   - Pricing and availability (set your price)
   - Properties (category, age rating)
   - Store listing (description, screenshots, privacy policy URL)
   - Packages (upload your `.msix`)
5. Click "Submit to the Store"

Review typically takes 3–7 business days.

---

## Step 10 — Auto-Updates (Recommended Before Launch)

The blueprint notes auto-updates are not implemented. Without this, customers must manually download and install every update.

**Add Tauri updater plugin:**
1. Add to `Cargo.toml`: `tauri-plugin-updater = "2"`
2. Add to `src-tauri/src/lib.rs`: register the updater plugin
3. Add to `tauri.conf.json`:
```json
{
  "plugins": {
    "updater": {
      "endpoints": ["https://your-update-server.com/updates/{{target}}/{{arch}}/{{current_version}}"],
      "pubkey": "YOUR_UPDATER_PUBLIC_KEY"
    }
  }
}
```
4. Host update manifests at your endpoint URL
5. The simplest hosting option: GitHub Releases + a small JSON manifest file

---

## Step 11 — Pricing

Options:
- **Free** (with no in-app purchases): simplest, but no revenue from Store
- **Paid** (one-time purchase): set a price in Partner Center — Microsoft takes 15% (reduced from 30% for smaller developers)
- **Free trial then paid**: best for pharmacy software — 14-day free trial, then purchase
- **Subscription**: requires implementing Microsoft Store subscription APIs (complex)

**Recommended:** One-time paid purchase. Pharmacy software buyers expect to own it outright, not subscribe.

---

## Checklist Before Submission

| Item | Status |
|------|--------|
| Fresh install wizard working (Spec 02) | ⬜ |
| All critical bugs fixed (Spec 01) | ⬜ |
| MSIX package created | ⬜ |
| Partner Center account active | ⬜ |
| Privacy policy URL live | ⬜ |
| App icons all present in src-tauri/icons/ | ⬜ |
| Store listing screenshots taken | ⬜ |
| Age rating questionnaire complete | ⬜ |
| App tested on a fresh Windows machine | ⬜ |
| devtools: false confirmed in tauri.conf.json | ⬜ |
