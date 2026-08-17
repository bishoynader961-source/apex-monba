// Typed License API service.
import { api } from "@/lib/api";
import type { LicenseValidationResult } from "@/types/contracts";

const BASE = "/api/v1/license";

export async function validateLicense(
  licenseKey: string,
  hardwareId: string,
): Promise<LicenseValidationResult> {
  const { data } = await api.post<LicenseValidationResult>(`${BASE}/validate`, {
    license_key: licenseKey,
    hardware_id: hardwareId,
  });
  return data;
}
