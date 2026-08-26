// Typed License API service.
import { api } from "@/lib/api";
import type {
  CreemCheckoutRequest,
  CreemCheckoutResponse,
  LicenseFileRequest,
  LicenseFileResponse,
  LicenseValidationResult,
} from "@/types/contracts";

const BASE = "/api/v1/license";
const LICENSES_BASE = "/api/v1/licenses";

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

export async function importLicenseFile(
  hardwareId: string,
  fileContent: string,
): Promise<LicenseFileResponse> {
  const body: LicenseFileRequest = { hardware_id: hardwareId, file_content: fileContent };
  const { data } = await api.post<LicenseFileResponse>(`${LICENSES_BASE}/activate-file`, body);
  return data;
}

export async function initiateCheckout(payload: CreemCheckoutRequest): Promise<CreemCheckoutResponse> {
  const { data } = await api.post<CreemCheckoutResponse>(`${BASE}/checkout`, payload);
  return data;
}
