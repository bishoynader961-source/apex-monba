"""Local drug database for clinical decision support (M98-B).

Provides:
- ``parse_allergies`` — turn the free-text ``patients.patient_allergies`` column
  into a normalised tag list (consumed by ``PatientRead.allergy_alerts``).
- ``extract_ingredient`` — map a dispensed ``product_name`` to its primary
  active ingredient for allergy / DDI cross-checking.
- ``check_allergy_match`` — return human-readable warning strings when a
  dispensed drug's ingredient matches a patient's allergy tags.
- ``DDI_INTERACTIONS`` — a small seed table of contraindication-level drug–drug
  interactions (ingredient-pair → warning text).

Design decisions:
- No external API (RxNorm / First Databank) — fully offline, seeded locally.
- Allergy matching is **non-blocking**: warnings surface as ``allergy_flags`` on
  ``DispenseRead``; the pharmacist reviews and overrides (logged to audit).
- ``extract_ingredient`` falls back to the first whitespace-delimited token of
  the product name when the drug is not in the seed map, so never-stocked drugs
  still get a best-effort check.
"""
from __future__ import annotations

import re

_DRUG_INGREDIENT_MAP: dict[str, str] = {
    "aspirin": "aspirin",
    "ibuprofen": "ibuprofen",
    "acetaminophen": "acetaminophen",
    "metformin": "metformin",
    "lisinopril": "lisinopril",
    "enalapril": "lisinopril",
    "atenolol": "atenolol",
    "metoprolol": "metoprolol",
    "atorvastatin": "atorvastatin",
    "simvastatin": "simvastatin",
    "rosuvastatin": "rosuvastatin",
    "amoxicillin": "amoxicillin",
    "amoxicillin-clavulanate": "amoxicillin",
    "azithromycin": "azithromycin",
    "ciprofloxacin": "ciprofloxacin",
    "levofloxacin": "levofloxacin",
    "warfarin": "warfarin",
    "heparin": "heparin",
    "enoxaparin": "enoxaparin",
    "digoxin": "digoxin",
    "furosemide": "furosemide",
    "hydrochlorothiazide": "hydrochlorothiazide",
    "losartan": "losartan",
    "valsartan": "valsartan",
    "amlodipine": "amlodipine",
    "nifedipine": "nifedipine",
    "clopidogrel": "clopidogrel",
    "omeprazole": "omeprazole",
    "esomeprazole": "esomeprazole",
    "pantoprazole": "pantoprazole",
    "ranitidine": "ranitidine",
    "famotidine": "famotidine",
    "albuterol": "albuterol",
    "ipratropium": "ipratropium",
    "fluticasone": "fluticasone",
    "budesonide": "budesonide",
    "prednisone": "prednisone",
    "methylprednisolone": "methylprednisolone",
    "loratadine": "loratadine",
    "cetirizine": "cetirizine",
    "fexofenadine": "fexofenadine",
    "diphenhydramine": "diphenhydramine",
    "chlorpheniramine": "chlorpheniramine",
    "pseudoephedrine": "pseudoephedrine",
    "phenylephrine": "phenylephrine",
    "dextromethorphan": "dextromethorphan",
    "guaifenesin": "guaifenesin",
    "loperamide": "loperamide",
    "laxative": "bisacodyl",
    "bisacodyl": "bisacodyl",
    "senna": "senna",
    "polyethylene glycol": "polyethylene glycol",
    "docusate": "docusate",
    "insulin": "insulin",
    "levothyroxine": "levothyroxine",
    "liothyronine": "liothyronine",
    "gabapentin": "gabapentin",
    "pregabalin": "pregabalin",
    "venlafaxine": "venlafaxine",
    "sertraline": "sertraline",
    "fluoxetine": "fluoxetine",
    "citalopram": "citalopram",
    "escitalopram": "escitalopram",
    "bupropion": "bupropion",
    "alprazolam": "alprazolam",
    "lorazepam": "lorazepam",
    "diazepam": "diazepam",
    "oxycodone": "oxycodone",
    "hydrocodone": "hydrocodone",
    "tramadol": "tramadol",
    "morphine": "morphine",
    "hydromorphone": "hydromorphone",
    "naproxen": "naproxen",
    "celecoxib": "celecoxib",
    "methotrexate": "methotrexate",
    "azathioprine": "azathioprine",
    "prednisolone": "prednisolone",
    "hydroxyzine": "hydroxyzine",
    "ondansetron": "ondansetron",
    "metoclopramide": "metoclopramide",
    "promethazine": "promethazine",
    "cyclobenzaprine": "cyclobenzaprine",
    "baclofen": "baclofen",
    "tizanidine": "tizanidine",
}


_DDI_INTERACTIONS: dict[str, list[tuple[str, str]]] = {
    "warfarin": [("aspirin", "Increased bleeding risk with aspirin"),
                 ("ibuprofen", "Increased bleeding risk with NSAIDs"),
                 ("naproxen", "Increased bleeding risk with NSAIDs"),
                 ("clopidogrel", "Increased bleeding risk with clopidogrel"),
                 ("diphenhydramine", "Additive sedation / bleeding risk with diphenhydramine")],
    "aspirin": [("warfarin", "Increased bleeding risk with warfarin"),
                ("clopidogrel", "Additive antiplatelet effect — bleeding risk"),
                ("ibuprofen", "Reduced cardioprotection with concurrent NSAIDs")],
    "lisinopril": [("potassium", "Risk of hyperkalemia with potassium supplements/sparing diuretics"),
                   ("spironolactone", "Risk of hyperkalemia with spironolactone")],
    "digoxin": [("furosemide", "Increased digoxin levels with loop diuretic"),
                ("amiodarone", "Increased digoxin levels with amiodarone — monitor for toxicity")],
    "insulin": [("beta-blocker", "Beta-blockers may mask hypoglycemia symptoms — use caution"),
                ("prednisone", "Corticosteroids may increase insulin requirements")],
    "prednisone": [("insulin", "Corticosteroids may increase insulin requirements"),
                   ("omeprazole", "Monitor for increased infection risk"),
                   ("warfarin", "May increase INR with warfarin")],
    "omeprazole": [("clopidogrel", "PPIs reduce clopidogrel antiplatelet activation"),
                   ("warfarin", "Monitor INR — PPIs can displace warfarin from protein binding")],
    "phenytoin": [("amiodarone", "Amiodarone increases phenytoin levels — toxicity risk"),
                  ("warfarin", "May increase or decrease warfarin effects")],
}


_ALLERGY_PATTERN = re.compile(r"[;,]\s*|\s+and\s+|/")


def parse_allergies(text: str) -> list[str]:
    """Parse a free-text allergy string into normalised lowercase tags.

    Handles comma-, semicolon-, slash-, and "and"-separated lists.
    Example: ``"Penicillin, Aspirin and Codeine"`` → ``["penicillin", "aspirin", "codeine"]``
    """
    if not text or not text.strip():
        return []
    parts = _ALLERGY_PATTERN.split(text)
    tags: list[str] = []
    for part in parts:
        cleaned = part.strip().lower()
        if cleaned and cleaned not in tags:
            tags.append(cleaned)
    return tags


def extract_ingredient(product_name: str) -> str:
    """Map a dispensed product_name to its primary active ingredient.

    First checks the seed ``_DRUG_INGREDIENT_MAP``; falls back to the first
    whitespace-delimited token of the product name (lowercased).
    """
    key = product_name.strip().lower()
    if key in _DRUG_INGREDIENT_MAP:
        return _DRUG_INGREDIENT_MAP[key]
    first_token = key.split()[0] if key else ""
    return _DRUG_INGREDIENT_MAP.get(first_token, first_token)


def check_allergy_match(product_name: str, allergies_text: str) -> list[str]:
    """Return warning strings when *product_name* matches a patient's allergy tags.

    Non-blocking: returns ``[]`` when there is no match; the caller surfaces the
    warnings as ``allergy_flags`` on ``DispenseRead`` for pharmacist review.
    """
    tags = parse_allergies(allergies_text)
    if not tags:
        return []
    ingredient = extract_ingredient(product_name)
    flags: list[str] = []
    if ingredient in tags:
        flags.append(f"Allergy alert: patient has documented allergy to {ingredient}")
    if ingredient in _DDI_INTERACTIONS:
        for interactant, warning in _DDI_INTERACTIONS[ingredient]:
            if interactant in tags:
                flags.append(f"Drug interaction alert: {warning}")
    return flags
