# Privacy Policy for Pharmacy Suite

**Last Updated:** September 21, 2026  
**Version:** 1.0

## 1. Introduction

Pharmacy Suite ("we", "our", "us") is committed to protecting your privacy. This Privacy Policy explains how we collect, use, disclose, and safeguard your information when you use our desktop pharmacy management application.

## 2. Information We Collect

### 2.1 Data You Provide Directly
- **Account Information**: Username, password (hashed), display name, role
- **Pharmacy Profile**: Pharmacy name, address, phone number, license number
- **Patient Data**: Names, contact information, prescriptions, insurance details (stored locally on your device)
- **Inventory Data**: Product names, quantities, pricing, supplier information

### 2.2 Automatically Collected Data
- **Application Usage**: Feature usage, error logs, performance metrics (local only)
- **Device Information**: OS version, screen resolution, locale settings
- **Network Information**: Local IP address for multi-terminal sync (LAN only)

## 3. How We Use Your Information

All data processing occurs **locally on your device** or within your **local network**. We do not transmit your pharmacy data to external servers.

- **Core Functionality**: Prescription processing, inventory management, POS transactions
- **Multi-Terminal Sync**: LAN-only synchronization between authorized terminals
- **Reporting**: Sales analytics, inventory reports, expiry alerts
- **Compliance**: Audit trails for regulatory requirements (HIPAA, state pharmacy boards)

## 4. Data Storage & Security

### 4.1 Local Storage
- SQLite database stored in OS app data directory (`%APPDATA%\PharmacySuite\PharmacySuite\pharmacy.db`)
- Passwords hashed with bcrypt (cost factor 12)
- PINs protected with Argon2id + device-bound pepper
- Database encryption available via OS-level encryption (BitLocker/FileVault)

### 4.2 Network Communication
- TLS 1.3 for all local network communication
- No external API calls for pharmacy data
- Optional Paddle webhook for license verification only

### 4.3 Backup & Export
- Encrypted backup files (AES-256)
- Export formats: CSV, PDF, JSON
- User-controlled backup schedule and destination

## 5. Data Sharing & Disclosure

We **do not sell, rent, or share** your pharmacy data with third parties.

**Exceptions:**
- Legal compliance (court orders, regulatory audits)
- License verification with Paddle (email, license key only)
- Multi-terminal sync within your authorized LAN

## 6. Your Rights

### 6.1 Data Access & Portability
- Full database export (CSV, JSON, SQL)
- Patient record export (HL7, CCD formats)
- Report generation and export

### 6.2 Data Deletion
- Individual record deletion (soft delete with audit trail)
- Complete database wipe (Settings → Danger Zone)
- Automatic purge of audit logs after configurable retention

### 6.3 Consent Management
- Opt-in for anonymous usage analytics
- Patient consent tracking for communications
- Marketing opt-out (default: opted out)

## 7. Children's Privacy

Pharmacy Suite is not directed to children under 13. We do not knowingly collect personal information from children. Patient data may include minors' prescription information as part of normal pharmacy operations.

## 8. International Data Transfers

No international data transfers occur. All data remains within your local network and device.

## 9. Security Measures

- **Encryption**: AES-256 for backups, TLS 1.3 for network
- **Authentication**: bcrypt + Argon2id, device-bound PIN pepper
- **Authorization**: Role-based access control (RBAC) with wildcard admin
- **Audit Trail**: Tamper-evident hash chain for all modifications
- **Session Management**: Configurable idle/absolute timeouts, concurrent session limits

## 10. Compliance

- **HIPAA**: PHI handled per Security Rule (encryption, access controls, audit logs)
- **State Pharmacy Boards**: Audit trails, prescription records, controlled substance tracking
- **PCI DSS**: No cardholder data stored (payment processing via external terminals)
- **GDPR**: Data subject rights supported (access, rectification, erasure, portability)

## 11. Third-Party Services

| Service | Purpose | Data Shared |
|---------|---------|-------------|
| Paddle | License verification | Email, license key, device ID |
| DigiCert | Timestamping | File hash only |
| Windows SDK | Code signing | Certificate only |

## 12. Changes to This Policy

We will notify you of material changes via in-app notification and update the "Last Updated" date. Continued use constitutes acceptance.

## 13. Contact Us

**Data Protection Officer**: privacy@pharmacysuite.com  
**Support**: https://github.com/pharmacysuite/pharmacysuite/issues  
**Mail**: Pharmacy Suite Privacy, 123 Main St, Anytown, ST 12345

---

*This policy is effective as of the "Last Updated" date above.*