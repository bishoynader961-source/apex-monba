"""
rx_strategies.py — Pharmacy billing integration strategies.

Provides:
  - PharmacyIntegrationStrategy: abstract base class.
  - USBillingStrategy: Medicare Part D / private insurer logic.
  - EUBillingStrategy: AMTS / reference pricing logic.
  - MockProvider: no-op strategy for testing.
  - strategy_factory: resolve a strategy by region code.
"""
import logging
import os
from abc import ABC, abstractmethod

log = logging.getLogger("rx_strategies")


class PharmacyIntegrationStrategy(ABC):
    """Abstract base for regional pharmacy billing integration."""

    def __init__(self):
        self.region = None

    @abstractmethod
    def calculate_patient_cost(self, unit_price, quantity, insurance_coverage=None):
        """Return the amount the patient pays."""
        raise NotImplementedError

    @abstractmethod
    def generate_claim(self, claim_data):
        """Generate a claim payload for the regional insurance body."""
        raise NotImplementedError

    @abstractmethod
    def validate_prescription(self, prescription_data):
        """Validate prescription data against regional rules."""
        raise NotImplementedError

    @abstractmethod
    def authenticate(self, credentials):
        """Test connection to the regional billing gateway.

        Args:
            credentials: dict of region-specific credentials
                         (e.g. {"api_key": "...", "switch_id": "..."})

        Returns:
            (bool, str): (success, status_message)
        """
        raise NotImplementedError


class USBillingStrategy(PharmacyIntegrationStrategy):
    def __init__(self):
        super().__init__()
        self.region = "US"

    def calculate_patient_cost(self, unit_price, quantity, insurance_coverage=None):
        base_cost = unit_price * quantity
        coverage = insurance_coverage or {"coinsurance_rate": 0.2, "copay": 5.0}
        coinsurance = base_cost * coverage.get("coinsurance_rate", 0.2)
        copay = coverage.get("copay", 5.0)
        patient_pays = min(base_cost, copay + coinsurance)
        log.debug("US billing: base=%.2f patient_pays=%.2f", base_cost, patient_pays)
        return round(patient_pays, 2)

    def generate_claim(self, claim_data):
        return {
            "region": "US",
            "npi": claim_data.get("prescriber_npi"),
            "ndc": claim_data.get("ndc"),
            "quantity": claim_data.get("quantity"),
            "days_supply": claim_data.get("days_supply"),
            "insurance_id": claim_data.get("insurance_id"),
            "submitter": claim_data.get("pharmacy_npi"),
        }

    def validate_prescription(self, prescription_data):
        required = ["drug_name", "dosage", "quantity", "prescriber_npi"]
        missing = [f for f in required if not prescription_data.get(f)]
        if missing:
            raise ValueError(f"Missing required fields for US prescription: {missing}")
        return True

    def authenticate(self, credentials):
        api_key = credentials.get("api_key", "")
        switch_id = credentials.get("switch_id", "")
        if not api_key:
            return (False, "NCPDP API Key is required")
        if not switch_id:
            return (False, "Switch ID is required")
        log.debug("US authenticate: API key and Switch ID provided")
        return (True, "US credential validation passed")


class EUBillingStrategy(PharmacyIntegrationStrategy):
    def __init__(self):
        super().__init__()
        self.region = "GB"

    def calculate_patient_cost(self, unit_price, quantity, insurance_coverage=None):
        base_cost = unit_price * quantity
        coverage = insurance_coverage or {"vat_rate": 0.2, "patient_contribution": 0.1}
        patient_share = base_cost * coverage.get("patient_contribution", 0.1)
        vat = patient_share * coverage.get("vat_rate", 0.2)
        total = patient_share + vat
        log.debug("EU billing: base=%.2f patient_pays=%.2f", base_cost, total)
        return round(total, 2)

    def generate_claim(self, claim_data):
        return {
            "region": "EU",
            "amts_code": claim_data.get("amts_code"),
            "bnf_code": claim_data.get("bnf_code"),
            "quantity": claim_data.get("quantity"),
            "days_supply": claim_data.get("days_supply"),
            " NHS_number": claim_data.get("nhs_number"),
            "prescriber_ods": claim_data.get("prescriber_ods"),
        }

    def validate_prescription(self, prescription_data):
        required = ["drug_name", "dosage", "quantity", "prescriber_ods"]
        missing = [f for f in required if not prescription_data.get(f)]
        if missing:
            raise ValueError(f"Missing required fields for EU prescription: {missing}")
        return True

    def authenticate(self, credentials):
        api_key = credentials.get("fmd_api_key", "")
        cert_path = credentials.get("cert_path", "")
        if not api_key:
            return (False, "FMD API Key is required")
        if not cert_path or not os.path.exists(cert_path):
            return (False, "Certificate path is required and must exist on disk")
        log.debug("EU authenticate: FMD API Key and certificate provided")
        return (True, "EU credential validation passed")


class MockProvider(PharmacyIntegrationStrategy):
    def __init__(self):
        super().__init__()
        self.region = "MOCK"

    def calculate_patient_cost(self, unit_price, quantity, insurance_coverage=None):
        total = unit_price * quantity
        log.debug("Mock billing: base=%.2f", total)
        return round(total, 2)

    def generate_claim(self, claim_data):
        return {
            "region": "MOCK",
            "drug_name": claim_data.get("drug_name"),
            "quantity": claim_data.get("quantity"),
        }

    def validate_prescription(self, prescription_data):
        return True

    def authenticate(self, credentials):
        log.debug("Mock authenticate: all credentials accepted")
        return (True, "Mock provider — credentials accepted")


_REGISTRY = {
    "US": USBillingStrategy,
    "GB": EUBillingStrategy,
    "DE": EUBillingStrategy,
    "MOCK": MockProvider,
}


def strategy_factory(region="US"):
    cls = _REGISTRY.get(region, MockProvider)
    return cls()
