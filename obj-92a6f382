"""Region Billing Strategy Service.

Mirrors legacy rx_strategies.py with the same calculation logic but integrated
into the FastAPI service layer. Provides US (Medicare Part D), EU/GB (AMTS),
and MOCK strategies for patient cost calculation, claim generation, prescription
validation, and credential authentication.
"""
from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Optional

from app.shared.schemas import (
    ClaimGenerationRequest,
    ClaimGenerationResult,
    CredentialValidationRequest,
    CredentialValidationResult,
    InsuranceCoverage,
    PatientCostRequest,
    PatientCostResult,
    PrescriptionValidationRequest,
    PrescriptionValidationResult,
)

log = logging.getLogger("region_strategy")


# ── Abstract Base Strategy ────────────────────────────────────────────────────

class PharmacyIntegrationStrategy(ABC):
    """Abstract base for regional pharmacy billing integration."""

    def __init__(self) -> None:
        self.region: str = "UNKNOWN"

    @abstractmethod
    def calculate_patient_cost(
        self,
        unit_price: Decimal,
        quantity: int,
        insurance_coverage: Optional[InsuranceCoverage] = None,
    ) -> PatientCostResult:
        """Return the amount the patient pays with detailed breakdown."""
        raise NotImplementedError

    @abstractmethod
    def generate_claim(self, payload: ClaimGenerationRequest) -> ClaimGenerationResult:
        """Generate a claim payload for the regional insurance body."""
        raise NotImplementedError

    @abstractmethod
    def validate_prescription(
        self, payload: PrescriptionValidationRequest
    ) -> PrescriptionValidationResult:
        """Validate prescription data against regional rules."""
        raise NotImplementedError

    @abstractmethod
    def authenticate(
        self, payload: CredentialValidationRequest
    ) -> CredentialValidationResult:
        """Test connection to the regional billing gateway."""
        raise NotImplementedError


# ── US Billing Strategy (Medicare Part D / Private Insurer) ──────────────────

class USBillingStrategy(PharmacyIntegrationStrategy):
    """US Medicare Part D / private insurer billing logic."""

    def __init__(self) -> None:
        self.region = "US"

    def calculate_patient_cost(
        self,
        unit_price: Decimal,
        quantity: int,
        insurance_coverage: Optional[InsuranceCoverage] = None,
    ) -> PatientCostResult:
        base_cost = unit_price * quantity
        coverage = insurance_coverage or InsuranceCoverage(
            coinsurance_rate=0.2,
            copay=5.0,
        )

        coinsurance_rate = coverage.coinsurance_rate or 0.2
        copay = coverage.copay or 5.0

        coinsurance = base_cost * Decimal(str(coinsurance_rate))
        patient_pays = min(base_cost, Decimal(str(copay)) + coinsurance)
        patient_pays = patient_pays.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        insurance_pays = (base_cost - patient_pays).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        log.debug(
            "US billing: base=%.2f coinsurance=%.2f copay=%.2f patient_pays=%.2f",
            base_cost,
            coinsurance,
            copay,
            patient_pays,
        )

        return PatientCostResult(
            patient_pays=float(patient_pays),
            insurance_pays=float(insurance_pays),
            total_cost=float(base_cost),
            breakdown={
                "base_cost": float(base_cost),
                "coinsurance": float(coinsurance.quantize(Decimal("0.01"))),
                "copay": float(copay),
                "coinsurance_rate": coinsurance_rate,
            },
            region="US",
        )

    def generate_claim(self, payload: ClaimGenerationRequest) -> ClaimGenerationResult:
        claim = {
            "region": "US",
            "npi": payload.prescriber_npi,
            "ndc": payload.ndc,
            "quantity": payload.quantity,
            "days_supply": payload.days_supply,
            "insurance_id": payload.insurance_id,
            "submitter": payload.pharmacy_npi,
        }
        return ClaimGenerationResult(region="US", claim=claim)

    def validate_prescription(
        self, payload: PrescriptionValidationRequest
    ) -> PrescriptionValidationResult:
        required = ["drug_name", "dosage", "quantity", "prescriber_npi"]
        missing = [f for f in required if not payload.model_dump().get(f)]
        if missing:
            return PrescriptionValidationResult(
                valid=False,
                errors=[f"Missing required fields for US prescription: {missing}"],
            )
        return PrescriptionValidationResult(valid=True)

    def authenticate(
        self, payload: CredentialValidationRequest
    ) -> CredentialValidationResult:
        api_key = payload.credentials.get("api_key", "")
        switch_id = payload.credentials.get("switch_id", "")
        if not api_key:
            return CredentialValidationResult(
                success=False,
                message="NCPDP API Key is required",
            )
        if not switch_id:
            return CredentialValidationResult(
                success=False,
                message="Switch ID is required",
            )
        log.debug("US authenticate: API key and Switch ID provided")
        return CredentialValidationResult(
            success=True,
            message="US credential validation passed",
        )


# ── EU/GB Billing Strategy (AMTS / Reference Pricing) ────────────────────────

class EUBillingStrategy(PharmacyIntegrationStrategy):
    """EU AMTS / reference pricing logic (GB/DE)."""

    def __init__(self) -> None:
        self.region = "GB"  # Default to GB, DE uses same logic

    def calculate_patient_cost(
        self,
        unit_price: Decimal,
        quantity: int,
        insurance_coverage: Optional[InsuranceCoverage] = None,
    ) -> PatientCostResult:
        base_cost = unit_price * quantity
        coverage = insurance_coverage or InsuranceCoverage(
            vat_rate=0.2,
            patient_contribution=0.1,
        )

        vat_rate = coverage.vat_rate or 0.2
        patient_contribution = coverage.patient_contribution or 0.1

        patient_share = base_cost * Decimal(str(patient_contribution))
        vat = patient_share * Decimal(str(vat_rate))
        total = patient_share + vat
        total = total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        insurance_pays = (base_cost - total).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        log.debug(
            "EU billing: base=%.2f patient_share=%.2f vat=%.2f total=%.2f",
            base_cost,
            patient_share,
            vat,
            total,
        )

        return PatientCostResult(
            patient_pays=float(total),
            insurance_pays=float(insurance_pays),
            total_cost=float(base_cost),
            breakdown={
                "base_cost": float(base_cost),
                "patient_share": float(patient_share.quantize(Decimal("0.01"))),
                "vat": float(vat.quantize(Decimal("0.01"))),
                "vat_rate": vat_rate,
                "patient_contribution": patient_contribution,
            },
            region=self.region,
        )

    def generate_claim(self, payload: ClaimGenerationRequest) -> ClaimGenerationResult:
        claim = {
            "region": self.region,
            "amts_code": payload.amts_code,
            "bnf_code": payload.bnf_code,
            "quantity": payload.quantity,
            "days_supply": payload.days_supply,
            "nhs_number": payload.nhs_number,
            "prescriber_ods": payload.prescriber_ods,
        }
        return ClaimGenerationResult(region=self.region, claim=claim)

    def validate_prescription(
        self, payload: PrescriptionValidationRequest
    ) -> PrescriptionValidationResult:
        required = ["drug_name", "dosage", "quantity", "prescriber_ods"]
        missing = [f for f in required if not payload.model_dump().get(f)]
        if missing:
            return PrescriptionValidationResult(
                valid=False,
                errors=[f"Missing required fields for {self.region} prescription: {missing}"],
            )
        return PrescriptionValidationResult(valid=True)

    def authenticate(
        self, payload: CredentialValidationRequest
    ) -> CredentialValidationResult:
        api_key = payload.credentials.get("fmd_api_key", "")
        cert_path = payload.credentials.get("cert_path", "")
        if not api_key:
            return CredentialValidationResult(
                success=False,
                message="FMD API Key is required",
            )
        if not cert_path or not os.path.exists(cert_path):
            return CredentialValidationResult(
                success=False,
                message="Certificate path is required and must exist on disk",
            )
        log.debug("EU authenticate: FMD API Key and certificate provided")
        return CredentialValidationResult(
            success=True,
            message=f"{self.region} credential validation passed",
        )


# ── Mock Provider (Testing) ──────────────────────────────────────────────────

class MockProvider(PharmacyIntegrationStrategy):
    """No-op strategy for testing."""

    def __init__(self) -> None:
        self.region = "MOCK"

    def calculate_patient_cost(
        self,
        unit_price: Decimal,
        quantity: int,
        insurance_coverage: Optional[InsuranceCoverage] = None,
    ) -> PatientCostResult:
        total = (unit_price * quantity).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        log.debug("Mock billing: base=%.2f", total)
        return PatientCostResult(
            patient_pays=float(total),
            insurance_pays=0.0,
            total_cost=float(total),
            breakdown={"base_cost": float(total)},
            region="MOCK",
        )

    def generate_claim(self, payload: ClaimGenerationRequest) -> ClaimGenerationResult:
        claim = {
            "region": "MOCK",
            "drug_name": payload.drug_name,
            "quantity": payload.quantity,
        }
        return ClaimGenerationResult(region="MOCK", claim=claim)

    def validate_prescription(
        self, payload: PrescriptionValidationRequest
    ) -> PrescriptionValidationResult:
        return PrescriptionValidationResult(valid=True)

    def authenticate(
        self, payload: CredentialValidationRequest
    ) -> CredentialValidationResult:
        log.debug("Mock authenticate: all credentials accepted")
        return CredentialValidationResult(
            success=True,
            message="Mock provider — credentials accepted",
        )


# ── Strategy Factory ────────────────────────────────────────────────────────

_REGISTRY: dict[str, type[PharmacyIntegrationStrategy]] = {
    "US": USBillingStrategy,
    "GB": EUBillingStrategy,
    "DE": EUBillingStrategy,
    "MOCK": MockProvider,
}


def strategy_factory(region: str = "US") -> PharmacyIntegrationStrategy:
    """Resolve a strategy by region code (US, GB, DE, MOCK)."""
    cls = _REGISTRY.get(region.upper(), MockProvider)
    return cls()


class RegionStrategyService:
    """Service facade for region-aware billing operations."""

    def __init__(self) -> None:
        self._strategy_cache: dict[str, PharmacyIntegrationStrategy] = {}

    def _get_strategy(self, region: str) -> PharmacyIntegrationStrategy:
        region_key = region.upper()
        if region_key not in self._strategy_cache:
            self._strategy_cache[region_key] = strategy_factory(region_key)
        return self._strategy_cache[region_key]

    def calculate_patient_cost(
        self, payload: PatientCostRequest
    ) -> PatientCostResult:
        """Calculate patient out-of-pocket cost for the given region."""
        strategy = self._get_strategy(payload.region)
        return strategy.calculate_patient_cost(
            unit_price=Decimal(str(payload.unit_price)),
            quantity=payload.quantity,
            insurance_coverage=payload.insurance_coverage,
        )

    def generate_claim(self, payload: ClaimGenerationRequest) -> ClaimGenerationResult:
        """Generate a regional insurance claim payload."""
        strategy = self._get_strategy(payload.region)
        return strategy.generate_claim(payload)

    def validate_prescription(
        self, payload: PrescriptionValidationRequest
    ) -> PrescriptionValidationResult:
        """Validate prescription against regional rules."""
        strategy = self._get_strategy(payload.region)
        return strategy.validate_prescription(payload)

    def authenticate_credentials(
        self, payload: CredentialValidationRequest
    ) -> CredentialValidationResult:
        """Validate credentials for regional billing gateway."""
        strategy = self._get_strategy(payload.region)
        return strategy.authenticate(payload)

    def get_supported_regions(self) -> list[str]:
        """Return list of supported region codes."""
        return list(_REGISTRY.keys())