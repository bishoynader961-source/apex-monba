import json, os, sys

LOCALES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "locales")
en = json.load(open(os.path.join(LOCALES, "en.json"), encoding="utf-8"))
en_keys = set(en.keys())
ok = True
for lang in ["en", "de", "es", "fr", "pt", "ar"]:
    d = json.load(open(os.path.join(LOCALES, f"{lang}.json"), encoding="utf-8"))
    k = set(d.keys())
    parity = "OK" if k == en_keys else f"MISSING {en_keys - k} EXTRA {k - en_keys}"
    colon = d["change"].endswith(":") or d["patient_label"].endswith(":")
    checks = all([
        not colon,
        "change_due" in d, "select_a_patient" in d, "signed_in_as" in d,
        "field_pzn_code" in d, "tip_region_fields" in d,
    ])
    status = "OK" if (parity == "OK" and checks) else "FAIL"
    if status == "FAIL":
        ok = False
    print(f"{lang}: keys={len(k)} parity={parity} colon={colon} -> {status}")
    print(f"    change={d['change']!r} patient_label={d['patient_label']!r} change_due={d['change_due']!r}")
sys.exit(0 if ok else 1)
