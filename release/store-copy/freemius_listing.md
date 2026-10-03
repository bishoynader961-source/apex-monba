# Freemius Listing Copy — Pharmacy Suite (EN + AR)

Source of truth: code inspection 2026-10-03 (`release/DISCOVERY.md`, `release/AUDIT.md`). Every feature below exists in the code. Identity/pricing from `release/DECISIONS.md` (owner-approved). Do NOT add medical-advice claims (Freemius prohibited-products rule, cited in REPORT.md).

## App name
**Pharmacy Suite**

## Tagline (≤12 words)
- EN: **Run your whole pharmacy from one fast, offline desktop app.**
- AR: **أدر صيدليتك بالكامل من تطبيق سطح مكتب واحد سريع يعمل دون إنترنت.**

## Short description (2–3 sentences)
- EN: **Pharmacy Suite is an offline desktop application for managing a pharmacy's daily work: point-of-sale, inventory, expiry tracking, and reporting — with nothing stored in the cloud. Your data lives on your own machine, protected by encrypted backups, with an interface available in Arabic (full RTL) and five other languages. Built for Windows 10/11 and ready for multi-terminal pharmacies over a local network.**
- AR: **Pharmacy Suite هو تطبيق سطح مكتب يعمل دون إنترنت لإدارة أعمال الصيدلية اليومية: نقاط البيع، والمخزون، وتتبّع تواريخ الانتهاء، والتقارير — دون أي تخزين سحابي. بياناتك محفوظة على جهازك أنت، ومحمية بنسخ احتياطية مشفّرة، وواجهة البرنامج متاحة بالعربية (اتجاه من اليمين لليسار بالكامل) وخمس لغات أخرى. مصمم لويندوز 10/11 ويدعم أكثر من شاشة كاشير في نفس الصيدلية عبر الشبكة المحلية.**

## Feature list (8–10 bullets, each verified in code)

- EN:
  1. **Fast point-of-sale** — scan or search, sell, and print receipts in seconds; supports cash, card, and other payment methods.
  2. **Inventory with barcodes** — manufacturer and internal barcodes, low-stock status, stock adjustments, and receiving logs.
  3. **Expiry tracking & alerts** — every batch carries an expiry date; the dashboard surfaces soon-to-expire stock before it becomes a loss (FEFO-friendly batch views).
  4. **Multi-user with roles & permissions** — owner, pharmacist, and cashier roles with fine-grained permissions and an audit trail of who did what.
  5. **Multi-terminal on one local network** — connect several POS terminals to one pharmacy database with automatic device discovery and sync idempotency (no double sales).
  6. **Encrypted backups & one-click restore** — AES-256-GCM encrypted backups with a recovery key; restoring to a new machine is a guided flow.
  7. **Arabic out of the box (full RTL)** — 6 interface languages: Arabic, English, French, Spanish, German, Portuguese.
  8. **Patient records & dispense history** — keep customer profiles, purchase history, and dispensing records organized (record-keeping, not medical advice).
  9. **Reports & end-of-day** — sales reports, end-of-day summary, demand analytics, and gift cards/coupons.
  10. **Works offline, your data stays with you** — no cloud account needed for daily work; automatic app updates are optional and delivered digitally.

- AR:
  1. **نقطة بيع سريعة** — امسح الباركود أو ابحث، بِع، واطبع الفاتورة في ثوانٍ؛ يدعم النقدي والبطاقات وطرق دفع أخرى.
  2. **مخزون بالباركود** — باركود المصنّع وباركود داخلي، تنبيهات نقص المخزون، تسويات الكميات، وسجلّات الاستلام.
  3. **تتبّع تواريخ الانتهاء وتنبيهاتها** — كل تشغيلة (لوت) لها تاريخ انتهاء، ولوحة التحكم تُبرز الأدوية القريبة من الانتهاء قبل أن تصبح خسارة.
  4. **مستخدمون متعددون بأدوار وصلاحيات** — أدوار المالك والصيدلي والكاشير بصلاحيات دقيقة وسجل تدقيق لكل عملية.
  5. **أكثر من شاشة كاشير على نفس الشبكة المحلية** — اربط عدة أجهزة نقطة بيع بقاعدة بيانات واحدة مع مزامنة آمنة تمنع البيع المزدوج.
  6. **نسخ احتياطية مشفّرة واستعادة بضغطة واحدة** — نسخ AES-256-GCM مشفّرة بمفتاح استرداد، مع مسار موجّه للاستعادة على جهاز جديد.
  7. **العربية جاهزة من البداية (اتجاه كامل من اليمين لليسار)** — 6 لغات للواجهة: العربية، الإنجليزية، الفرنسية، الإسبانية، الألمانية، والبرتغالية.
  8. **ملفات العملاء وسجل الصرف** — نظّم بيانات العملاء وسجلّات الشراء والصرف في مكان واحد (سجلات إدارية، وليست استشارات طبية).
  9. **تقارير وإقفال يومي** — تقارير المبيعات، ملخص نهاية اليوم، تحليلات الطلب، وبطاقات الهدايا والكوبونات.
  10. **يعمل دون إنترنت وبياناتك تبقى معك** — لا حاجة لحساب سحابي في العمل اليومي، وتحديثات البرنامج اختيارية وتُسلَّم رقمياً.

## System requirements (verified against the Tauri v2 + FastAPI sidecar stack)

- OS: **Windows 10 or later (64-bit)** — installer ships the WebView2-based Tauri shell, the FastAPI sidecar, and the Node sidecar (NSIS/MSI).
- RAM: **4 GB minimum** (8 GB recommended for multi-terminal hosting).
- Disk: **~500 MB** for the app + local SQLite database growth.
- Display: 1366×768 minimum. Internet: needed only for purchase/activation, optional updates, and multi-terminal licensing checks — **not** for daily operation.

## FAQ (5 Q&A)

1. **EN: Does Pharmacy Suite need an internet connection to work?**
   AR: هل يحتاج Pharmacy Suite إلى اتصال بالإنترنت ليعمل؟
   - EN: **No.** Daily work — sales, inventory, reports — runs fully offline on your machine. The internet is only needed once for license activation and for optional updates.
   - AR: **لا.** العمل اليومي — البيع والمخزون والتقارير — يعمل بالكامل دون إنترنت على جهازك. يُستخدم الإنترنت فقط مرة واحدة لتفعيل الترخيص وللتحديثات الاختيارية.
2. **EN: Can I use it on more than one computer in the same pharmacy?**
   AR: هل يمكن استخدامه على أكثر من جهاز في نفس الصيدلية؟
   - EN: Yes. Multiple POS terminals connect over your local network to one shared database, with safeguards against duplicate sales. Each computer needs its own license.
   - AR: نعم. تتصل عدة أجهزة نقطة بيع عبر الشبكة المحلية بقاعدة بيانات واحدة، مع حماية من البيع المزدوج. يحتاج كل جهاز إلى ترخيص خاص به.
3. **EN: What happens when the 14-day trial ends?**
   AR: ماذا يحدث بعد انتهاء التجربة المجانية (14 يوماً)؟
   - EN: The app switches to read-only mode — you can view and export all your data, but not sell or edit, until you buy a license. You are never locked out of your data.
   - AR: يتحول البرنامج إلى وضع القراءة فقط — يمكنك عرض جميع بياناتك وتصديرها، لكن دون بيع أو تعديل، حتى تشتري الترخيص. لن نمنعك أبداً من الوصول إلى بياناتك.
4. **EN: Is the app available in Arabic, and does it really support right-to-left?**
   AR: هل البرنامج متوفر بالعربية؟ وهل يدعم الاتجاه من اليمين لليسار فعلاً؟
   - EN: Yes — Arabic is a first-class interface language with complete RTL layout, not just translated menus.
   - AR: نعم — العربية لغة أساسية في الواجهة مع تخطيط كامل من اليمين لليسار، وليست مجرد ترجمة للقوائم.
5. **EN: How do backups work, and can I move to a new computer?**
   AR: كيف تعمل النسخ الاحتياطية؟ وهل يمكن الانتقال إلى جهاز جديد؟
   - EN: One click creates an AES-256 encrypted backup with a recovery key. Restoring on a new computer is guided — install, restore the backup file with your key, and continue where you left off.
   - AR: بضغطة واحدة تُنشأ نسخة احتياطية مشفّرة AES-256 مع مفتاح استرداد. الاستعادة على جهاز جديد عملية موجّهة: ثبّت البرنامج، استعد النسخة بمفتاحك، وتابع من حيث توقفت.

## Keywords

- EN (10): `pharmacy management software`, `pharmacy POS`, `pharmacy inventory system`, `drug expiry tracking`, `pharmacy point of sale`, `medical store software`, `pharmacy billing software`, `prescription records software`, `pharmacy barcode system`, `offline pharmacy software`
- AR (10): `برنامج صيدلية`, `إدارة الصيدليات`, `برنامج كاشير صيدلية`, `نظام إدارة مخزون الأدوية`, `تتبع تاريخ انتهاء الأدوية`, `برنامج مبيعات الصيدلية`, `فواتير الصيدلية`, `نقاط بيع للصيدليات`, `سجلات الروشتات`, `برنامج صيدلية ويندوز`

## Pricing (from DECISIONS.md — do not change without owner approval)

- One-time license: **$149** per computer (app never expires; updates + email support included for 1 year).
- Optional renewal: **$59/year** for continued updates + support.
- Free trial: **14 days**. Refund: **14 days, no questions asked**.
- Publisher: **Apex Software** · Support: **pharmacypro.support@gmail.com** (48-hour response).
