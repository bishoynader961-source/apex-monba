# Privacy Policy — Pharmacy Suite

**Effective date:** [EFFECTIVE DATE — e.g., September 28, 2026]
**Applies to:** Pharmacy Suite desktop application (Windows) and Pharmacy Suite mobile companion app (Android)

---

## Overview

Pharmacy Suite is desktop-first software for independent pharmacies. It is built on a simple principle: **your pharmacy's data belongs to you and stays with you.**

The application runs on your pharmacy's own Windows computer. All records — patients, prescriptions, inventory, sales, and workers' compensation claims — are stored in a local database file on that machine. The software does not transmit patient data to us, to any cloud service, or to any third party. We could not look at your data even if we wanted to: there is no server of ours that receives it.

This policy explains exactly what the software stores, where, who can access it, and the limited circumstances in which anything ever leaves your pharmacy's network.

## Information collected and stored

Pharmacy Suite has no accounts or sign-up on our side and collects no information about you or your pharmacy on its own. Everything stored in the application is data that **you and your staff enter** in the normal course of running your pharmacy:

- **Patients:** names, contact details, insurance information, notes, and any custom fields your pharmacy configures.
- **Prescriptions:** electronic prescription service (EPCS) records, medication details, prescriber information, and dispensing history.
- **Inventory:** medicines, batch and expiry dates, stock movements, and supplier information.
- **Sales and payments:** point-of-sale transactions, receipts, refunds, and shift/cash-drawer records.
- **Workers' compensation claims:** claim details, totals, and related patient references.
- **Staff accounts:** user names, roles, and login credentials — passwords and PINs are stored only as irreversible cryptographic hashes, never in plain text.
- **Operational logs:** a tamper-evident audit trail of actions performed in the app (who did what and when), which is part of the product's record-keeping, not a data collection mechanism.

None of this is visible to, sent to, or stored by us.

## What we do not collect

Pharmacy Suite contains **no analytics, no telemetry, no usage tracking, and no advertising** of any kind. The app does not automatically send crash reports, error logs, or performance data anywhere. It does not profile users, does not use third-party trackers, and does not collect data from children or anyone else — because it does not send data anywhere at all.

## Where your data is stored

All application data is stored locally on the pharmacy's own computer:

- The database file (`pharmacy.db`) lives in the Pharmacy Suite application data folder on your Windows machine (for example, `%APPDATA%\PharmacySuite`).
- Application settings and window preferences are stored in local configuration files in the same location.
- Backups are created only when you choose to create them, are written to storage you control, and are never uploaded anywhere.

There is no cloud storage, no hosted database, and no off-site copy unless you make one yourself.

## Who has access to your data

- **Your pharmacy's staff:** access is controlled by the user accounts your pharmacy creates, each with role-based permissions (for example, a cashier account cannot reach administration pages). Only staff you authorize can view or change records.
- **Paired mobile devices:** the optional mobile companion app connects directly to your desktop computer over your **local pharmacy network only**. It is paired by an authorized staff member, sessions time out, and mobile login tokens are kept in the device's secure storage. No mobile traffic passes through our servers or the public internet.
- **Us (the vendor):** no one. We have no remote-access capability, no hosted copies of your data, and no telemetry channel. We cannot read, retrieve, or restore your records.

Anyone with physical access to the pharmacy's computer and its Windows login can access the machine's files, including the database — please secure the PC itself as you would any system holding patient records.

## How your data is protected

- **Encrypted backups (AES-256-GCM):** the encrypted backup feature protects your database with authenticated AES-256-GCM encryption. Each encrypted backup uses a fresh random 256-bit key that is shown to the administrator exactly once and is never stored by the application or transmitted to us. Without that key, the backup file cannot be opened — by anyone, including us. Restore verification rejects wrong or tampered keys.
- **Local-network-only mobile access:** the companion app works only against the desktop machine on your local network. There is no remote server endpoint for patient data.
- **Credential protection:** passwords and PINs are hashed (never stored reversibly), login sessions use short-lived signed tokens that expire, and mobile devices unlock with biometrics or device credentials where available.
- **Audit trail:** sensitive actions are recorded in a hash-chained audit log designed to make silent tampering detectable.
- **Honest limits:** the working database file on your PC is not itself encrypted at the application level. We recommend enabling disk encryption on the pharmacy computer (for example, Windows BitLocker) as standard practice for machines that hold patient records. Physical and Windows-account security of the machine remain your pharmacy's responsibility.

## Patient data and HIPAA considerations

Pharmacy Suite is designed so that **the vendor never creates, receives, maintains, or transmits your patients' protected health information (PHI)**. All patient data originates with your pharmacy, stays in your local database, and never leaves your control.

Because we do not hold or transmit any patient data, there is generally no patient data for us to process on your behalf, and no Business Associate Agreement with us is created by ordinary use of the software for that reason. Your pharmacy remains responsible for its own HIPAA compliance — including your risk analysis, workforce training, physical safeguards, and breach procedures — just as you would be for any local software.

Practical safeguards we recommend:

- Enable full-disk encryption (BitLocker) on the machine that stores the database.
- Use individual staff accounts with least-privilege roles; the app supports this natively.
- Keep encrypted backups on storage you control, and store recovery keys securely offline.
- Use the app's audit log when you need to review who accessed or changed records.

If you ever have questions about how the software handles patient data, contact us at the address below.

## The only external communications

Pharmacy Suite makes at most three kinds of outbound connections, none of which carry patient data:

1. **Optional update check.** If your pharmacy configures an update URL in settings, the desktop app can check that address for new versions. If no URL is configured, no check is made and nothing is sent. A check contacts only the address you chose and contains no pharmacy data; that server necessarily sees your computer's network address, as with any software-update request.
2. **Support email, initiated by you.** The Support page can open your own email client with a pre-filled message to our support address. A diagnostic report is included **only when a staff member chooses to copy and send it**, and it contains only technical information — application version, operating system version, and a short error-category code. It never contains patient data, prescription contents, passwords, or PINs. Email is composed in your email client; the app itself does not send email in the background.
3. **Microsoft Store distribution.** Installing or updating Pharmacy Suite through the Microsoft Store is handled by Windows under Microsoft's own privacy terms. The application adds nothing to that traffic.

That is the complete list. There are no other outbound connections.

## Data retention and deletion

We retain nothing, so there is nothing for us to delete. Your records persist on your computer until your pharmacy chooses to remove them:

- Records can be managed, corrected, or removed through the application's normal workflows.
- A complete export of your data is available at any time via the backup feature.
- Deleting the database file (or the Pharmacy Suite data folder) permanently removes all application data from the machine. Uninstalling the application by itself does **not** delete your database — the file remains yours.

If your pharmacy receives a patient request under HIPAA or applicable privacy law (such as an access or deletion request), it is handled by your pharmacy from your own local records — we have no copy to fulfill it from.

## Changes to this policy

If the software's data handling ever changes, we will update this policy and revise the effective date above before the change ships. The version of this policy distributed with the application and listed on the Microsoft Store listing will always describe the current behavior.

## Contact

Questions about privacy, security, or this policy:

- **Email:** pharmacypro.support@gmail.com
- **In the app:** Support page (dashboard → Support), which includes your application version and diagnostic tools

We will never ask you for your password, PIN, or backup recovery key.
