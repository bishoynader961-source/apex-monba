# Support Email Anti-Spoofing (SPF / DKIM / DMARC)

## The honest constraint first

Current support address: `pharmacypro.support@gmail.com` — a **gmail.com**
address. Google owns the `gmail.com` zone and already publishes SPF+DKIM+DMARC
for it. **We cannot and must not add DNS records for `gmail.com`**; anything we
tried would either be ignored or (if Google's records were ever wrong)
antagonize the actual owner. The practical consequence:

- Mail *from* `@gmail.com` cannot be spoofed in a way Gmail's own DMARC doesn't
  already cover (Google enforces `p=reject`-grade protection on its own zone).
- BUT free-mail support addresses weaken *brand verification*: a scammer can
  register `pharmacysuite.help@gmail.com`, `pharmacypro-support@outlook.com`, etc.
  The in-app Security Notice card (Support tab) is the primary defense against
  exactly this — users are told to trust the address shown **inside the app**,
  not in an inbound email.

## Recommended migration (the real fix): own the domain

Move support to **`support@pharmacysuite.app`** (domain already referenced by
the app identifier `com.pharmacysuite.app`). Then publish, in
`pharmacysuite.app` DNS:

```dns
; SPF — only the ESP may send as @pharmacysuite.app
pharmacysuite.app.            TXT  "v=spf1 include:<esp-include> -all"

; DKIM — provided per-selector by the email provider, e.g.:
s1._domainkey.pharmacysuite.app.  TXT  "v=DKIM1; k=rsa; p=<ESP-PUBLIC-KEY>"

; DMARC — reject unauthenticated mail, with reporting
_dmarc.pharmacysuite.app.     TXT  "v=DMARC1; p=reject; rua=mailto:dmarc-reports@pharmacysuite.app; adkim=s; aspf=s; pct=100"

; Explicit null records so nothing else can ever send as us (defensive):
*._domainkey.pharmacysuite.app. TXT "v=DKIM1; p="
pharmacysuite.app.            TXT  "v=spf1 -all"   ; ONLY IF a dedicated subdomain is used for the ESP instead
```

`p=reject` is appropriate from day one for a support domain: legitimate mail
comes from exactly one ESP, and quarantine only delays attackers' discovery
that spoofing fails.

## In-app defenses (shipped in this change)

1. **Support tab Security Notice** (`app/dashboard/support/page.tsx`): the
   exact spec text — never ask for password / `secret.key` / `pharmacy.db` —
   plus "we will never call you first". Served from
   `GET /api/v1/support/contact` (`security_notice` field) with a hardcoded
   client fallback so the notice survives a dead backend.
2. Support email is shown **inside the authenticated app**, not just on a
   public website — a spoofed email cannot change what the app displays.
3. Crash reports and diagnostics explicitly state what they contain (no
   passwords/patient data), so users are primed to refuse requests for anything
   beyond that.

## Migration checklist (when the domain move happens)

- [ ] Register/verify `pharmacysuite.app` with an email provider (ESP)
- [ ] Publish SPF/DKIM/DMARC above (via ESP dashboard or DNS)
- [ ] Update `support_route._DEFAULTS.support_email` + `SystemSetting` row
- [ ] Update in-app fallback constants (`support/page.tsx`)
- [ ] Keep `pharmacypro.support@gmail.com` as an auto-forwarding alias for 2
      release cycles, then announce deprecation in-app (Security Notice card)
- [ ] Monitor `rua` reports for a week at `p=none` → `p=quarantine` →
      `p=reject`
