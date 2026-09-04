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


# ── Phase 4: DUR — Drug-Drug Interaction Checking Against Active Meds ────────

class DdiAlert:
    """Structured DDI alert with severity."""

    __slots__ = ("drug_a", "drug_b", "severity", "warning")

    def __init__(self, drug_a: str, drug_b: str, severity: str, warning: str) -> None:
        self.drug_a = drug_a
        self.drug_b = drug_b
        self.severity = severity  # "contraindicated" | "major" | "moderate" | "minor"
        self.warning = warning

    def to_dict(self) -> dict[str, str]:
        return {
            "drug_a": self.drug_a,
            "drug_b": self.drug_b,
            "severity": self.severity,
            "warning": self.warning,
        }


# Expanded DDI table with severity levels: (interactant, severity, warning)
_DDI_TABLE: dict[str, list[tuple[str, str, str]]] = {
    "warfarin": [
        ("aspirin", "major", "Increased bleeding risk with aspirin"),
        ("ibuprofen", "major", "Increased bleeding risk with NSAIDs"),
        ("naproxen", "major", "Increased bleeding risk with NSAIDs"),
        ("celecoxib", "major", "Increased bleeding risk with COX-2 inhibitors"),
        ("clopidogrel", "major", "Increased bleeding risk with clopidogrel"),
        ("diphenhydramine", "moderate", "Additive sedation / bleeding risk"),
        ("omeprazole", "moderate", "Monitor INR — PPIs can displace warfarin"),
        ("phenytoin", "moderate", "May increase or decrease warfarin effects"),
        ("prednisone", "moderate", "May increase INR — monitor closely"),
    ],
    "aspirin": [
        ("warfarin", "major", "Increased bleeding risk with warfarin"),
        ("clopidogrel", "major", "Additive antiplatelet effect — bleeding risk"),
        ("ibuprofen", "moderate", "Reduced cardioprotection with concurrent NSAIDs"),
        ("naproxen", "moderate", "Reduced cardioprotection with concurrent NSAIDs"),
        ("methotrexate", "major", "Aspirin increases methotrexate toxicity"),
    ],
    "ibuprofen": [
        ("warfarin", "major", "Increased bleeding risk with warfarin"),
        ("aspirin", "moderate", "Reduced cardioprotection with concurrent aspirin"),
        ("lisinopril", "moderate", "NSAIDs reduce ACE inhibitor efficacy"),
        ("methotrexate", "major", "NSAIDs increase methotrexate toxicity"),
        ("lithium", "major", "NSAIDs increase lithium levels"),
    ],
    "naproxen": [
        ("warfarin", "major", "Increased bleeding risk with warfarin"),
        ("lisinopril", "moderate", "NSAIDs reduce ACE inhibitor efficacy"),
        ("methotrexate", "major", "NSAIDs increase methotrexate toxicity"),
        ("lithium", "major", "NSAIDs increase lithium levels"),
    ],
    "lisinopril": [
        ("potassium", "major", "Risk of hyperkalemia with potassium supplements"),
        ("spironolactone", "major", "Risk of hyperkalemia with spironolactone"),
        ("ibuprofen", "moderate", "NSAIDs reduce ACE inhibitor efficacy"),
        ("naproxen", "moderate", "NSAIDs reduce ACE inhibitor efficacy"),
    ],
    "enalapril": [
        ("potassium", "major", "Risk of hyperkalemia with potassium supplements"),
        ("spironolactone", "major", "Risk of hyperkalemia with spironolactone"),
    ],
    "digoxin": [
        ("furosemide", "moderate", "Increased digoxin levels with loop diuretic"),
        ("amiodarone", "major", "Increased digoxin levels — monitor for toxicity"),
        ("verapamil", "major", "Increased digoxin levels — bradycardia risk"),
    ],
    "insulin": [
        ("beta-blocker", "moderate", "Beta-blockers may mask hypoglycemia symptoms"),
        ("prednisone", "moderate", "Corticosteroids may increase insulin requirements"),
        ("ciprofloxacin", "moderate", "Fluoroquinolones may alter glucose levels"),
    ],
    "prednisone": [
        ("insulin", "moderate", "Corticosteroids may increase insulin requirements"),
        ("warfarin", "moderate", "May increase INR with warfarin"),
        ("omeprazole", "minor", "Monitor for increased infection risk"),
    ],
    "omeprazole": [
        ("clopidogrel", "major", "PPIs reduce clopidogrel antiplatelet activation"),
        ("warfarin", "moderate", "Monitor INR — PPIs can displace warfarin"),
    ],
    "phenytoin": [
        ("amiodarone", "major", "Amiodarone increases phenytoin levels — toxicity risk"),
        ("warfarin", "moderate", "May increase or decrease warfarin effects"),
        ("omeprazole", "moderate", "Omeprazole may increase phenytoin levels"),
    ],
    "methotrexate": [
        ("aspirin", "major", "Aspirin increases methotrexate toxicity"),
        ("ibuprofen", "major", "NSAIDs increase methotrexate toxicity"),
        ("naproxen", "major", "NSAIDs increase methotrexate toxicity"),
        ("trimethoprim", "major", "Increased methotrexate toxicity with trimethoprim"),
    ],
    "simvastatin": [
        ("amiodarone", "major", "Increased risk of rhabdomyolysis"),
        ("diltiazem", "major", "Increased risk of rhabdomyolysis"),
        ("clarithromycin", "major", "Increased risk of rhabdomyolysis"),
        ("itraconazole", "major", "Increased risk of rhabdomyolysis"),
    ],
    "atorvastatin": [
        ("clarithromycin", "moderate", "Monitor for increased statin levels"),
        ("itraconazole", "moderate", "Monitor for increased statin levels"),
    ],
    "clopidogrel": [
        ("omeprazole", "major", "PPIs reduce clopidogrel activation"),
        ("aspirin", "major", "Additive antiplatelet effect — bleeding risk"),
        ("warfarin", "major", "Increased bleeding risk"),
    ],
    "ciprofloxacin": [
        ("theophylline", "major", "Ciprofloxacin increases theophylline levels"),
        ("warfarin", "moderate", "May enhance anticoagulant effect"),
        ("antacid", "minor", "Reduce ciprofloxacin absorption — separate by 2h"),
    ],
    "levothyroxine": [
        ("calcium", "moderate", "Calcium supplements reduce levothyroxine absorption"),
        ("iron", "moderate", "Iron reduces levothyroxine absorption"),
        ("omeprazole", "minor", "PPIs may reduce levothyroxine absorption"),
    ],
    "gabapentin": [
        ("opioid", "major", "Risk of respiratory depression — CNS depression additive"),
    ],
    "pregabalin": [
        ("opioid", "major", "Risk of respiratory depression — CNS depression additive"),
    ],
}

# Therapeutic class mapping for duplicate therapy detection
_THERAPEUTIC_CLASSES: dict[str, str] = {
    "aspirin": "NSAID",
    "ibuprofen": "NSAID",
    "naproxen": "NSAID",
    "celecoxib": "NSAID",
    "diclofenac": "NSAID",
    "lisinopril": "ACE Inhibitor",
    "enalapril": "ACE Inhibitor",
    "ramipril": "ACE Inhibitor",
    "losartan": "ARB",
    "valsartan": "ARB",
    "irbesartan": "ARB",
    "metoprolol": "Beta Blocker",
    "atenolol": "Beta Blocker",
    "propranolol": "Beta Blocker",
    "carvedilol": "Beta Blocker",
    "amlodipine": "Calcium Channel Blocker",
    "nifedipine": "Calcium Channel Blocker",
    "diltiazem": "Calcium Channel Blocker",
    "verapamil": "Calcium Channel Blocker",
    "simvastatin": "Statin",
    "atorvastatin": "Statin",
    "rosuvastatin": "Statin",
    "pravastatin": "Statin",
    "omeprazole": "PPI",
    "esomeprazole": "PPI",
    "pantoprazole": "PPI",
    "lansoprazole": "PPI",
    "ranitidine": "H2 Blocker",
    "famotidine": "H2 Blocker",
    "sertraline": "SSRI",
    "fluoxetine": "SSRI",
    "citalopram": "SSRI",
    "escitalopram": "SSRI",
    "paroxetine": "SSRI",
    "venlafaxine": "SNRI",
    "duloxetine": "SNRI",
    "amoxicillin": "Penicillin",
    "amoxicillin-clavulanate": "Penicillin",
    "ampicillin": "Penicillin",
    "azithromycin": "Macrolide",
    "clarithromycin": "Macrolide",
    "erythromycin": "Macrolide",
    "ciprofloxacin": "Fluoroquinolone",
    "levofloxacin": "Fluoroquinolone",
    "moxifloxacin": "Fluoroquinolone",
    "furosemide": "Loop Diuretic",
    "bumetanide": "Loop Diuretic",
    "torsemide": "Loop Diuretic",
    "hydrochlorothiazide": "Thiazide Diuretic",
    "metformin": "Biguanide",
    "glipizide": "Sulfonylurea",
    "glyburide": "Sulfonylurea",
    "glimepiride": "Sulfonylurea",
    "warfarin": "Anticoagulant",
    "heparin": "Anticoagulant",
    "enoxaparin": "Anticoagulant",
    "apixaban": "DOAC",
    "rivaroxaban": "DOAC",
    "oxycodone": "Opioid",
    "hydrocodone": "Opioid",
    "morphine": "Opioid",
    "tramadol": "Opioid",
    "hydromorphone": "Opioid",
    "fentanyl": "Opioid",
    "alprazolam": "Benzodiazepine",
    "lorazepam": "Benzodiazepine",
    "diazepam": "Benzodiazepine",
    "clonazepam": "Benzodiazepine",
    "prednisone": "Corticosteroid",
    "prednisolone": "Corticosteroid",
    "methylprednisolone": "Corticosteroid",
    "dexamethasone": "Corticosteroid",
    "levothyroxine": "Thyroid Hormone",
    "liothyronine": "Thyroid Hormone",
}


def check_drug_interactions(
    product_name: str, active_medications: list[str]
) -> list[DdiAlert]:
    """Check a newly dispensed drug against the patient's active medications for DDIs.

    ``active_medications`` is a list of product names the patient is currently taking
    (from recent dispense history). Returns a list of ``DdiAlert`` objects with
    severity levels. Non-blocking — all alerts are advisory for pharmacist review.
    """
    if not active_medications:
        return []

    ingredient = extract_ingredient(product_name)
    if not ingredient:
        return []

    alerts: list[DdiAlert] = []
    seen_pairs: set[tuple[str, ...]] = set()

    for active_name in active_medications:
        active_ingredient = extract_ingredient(active_name)
        if not active_ingredient or active_ingredient == ingredient:
            continue

        # Check both directions of the interaction
        pair = tuple(sorted([ingredient, active_ingredient]))
        if pair in seen_pairs:
            continue

        # Forward: new drug interacts with active drug
        if ingredient in _DDI_TABLE:
            for interactant, severity, warning in _DDI_TABLE[ingredient]:
                if interactant == active_ingredient:
                    alerts.append(DdiAlert(ingredient, active_ingredient, severity, warning))
                    seen_pairs.add(pair)
                    break

        # Reverse: active drug interacts with new drug
        if active_ingredient in _DDI_TABLE and pair not in seen_pairs:
            for interactant, severity, warning in _DDI_TABLE[active_ingredient]:
                if interactant == ingredient:
                    alerts.append(DdiAlert(active_ingredient, ingredient, severity, warning))
                    seen_pairs.add(pair)
                    break

    return alerts


def check_duplicate_therapy(
    product_name: str, active_medications: list[str]
) -> list[str]:
    """Check if the newly dispensed drug duplicates the therapeutic class of an active med.

    Returns warning strings for the pharmacist to review. Non-blocking.
    """
    if not active_medications:
        return []

    ingredient = extract_ingredient(product_name)
    new_class = _THERAPEUTIC_CLASSES.get(ingredient)
    if not new_class:
        return []

    warnings: list[str] = []
    for active_name in active_medications:
        active_ingredient = extract_ingredient(active_name)
        active_class = _THERAPEUTIC_CLASSES.get(active_ingredient)
        if active_class and active_class == new_class and active_ingredient != ingredient:
            warnings.append(
                f"Duplicate therapy: both {ingredient} and {active_ingredient} are {new_class}"
            )

    return warnings
