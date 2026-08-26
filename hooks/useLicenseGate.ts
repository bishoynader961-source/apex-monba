"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";

import { validateLicense } from "@/lib/api/license";
import { getDeviceId } from "@/lib/deviceId";

export const LICENSED_PATHS = ["/dashboard", "/pos"] as const;
export const LICENSE_KEY_STORAGE_KEY = "pp_license_key";

export interface LicenseGateState {
  shouldGate: boolean;
  loading: boolean;
  licensed: boolean;
}

/**
 * Pure logic for computing the license-gate decision tree.
 * Extracted into a standalone function so it can be unit-tested without
 * React rendering (the project's vitest runs in the "node" environment).
 *
 * @param requireLicense  — true when NEXT_PUBLIC_REQUIRE_LICENSE !== "false"
 * @param pathname         — current URL pathname from usePathname()
 * @param licenseKey    — raw value from localStorage (string or null)
 */
export function computeLicenseGateState(
  requireLicense: boolean,
  pathname: string,
  licenseKey: string | null,
): LicenseGateState {
  const shouldGate =
    requireLicense && LICENSED_PATHS.some((p) => pathname.startsWith(p));

  if (!shouldGate) {
    return { shouldGate: false, loading: false, licensed: true };
  }
  if (!licenseKey) {
    return { shouldGate: true, loading: false, licensed: false };
  }
  return { shouldGate: true, loading: true, licensed: false };
}

export function useLicenseGate(): LicenseGateState {
  const pathname = usePathname();
  const requireLicense = process.env.NEXT_PUBLIC_REQUIRE_LICENSE !== "false";
  const licenseKey =
    typeof window !== "undefined"
      ? window.localStorage.getItem(LICENSE_KEY_STORAGE_KEY)
      : null;

  const [state, setState] = useState<LicenseGateState>(() =>
    computeLicenseGateState(requireLicense, pathname, licenseKey),
  );

  useEffect(() => {
    const target = computeLicenseGateState(requireLicense, pathname, licenseKey);

    if (!target.shouldGate) {
      setState({ shouldGate: false, loading: false, licensed: true });
      return;
    }

    if (!licenseKey) {
      setState({ shouldGate: true, loading: false, licensed: false });
      return;
    }

    // Validate against the backend.
    setState({ shouldGate: true, loading: true, licensed: false });
    const hardwareId = getDeviceId();

    void validateLicense(licenseKey, hardwareId)
      .then(() =>
        setState({ shouldGate: true, loading: false, licensed: true }),
      )
      .catch(() =>
        setState({ shouldGate: true, loading: false, licensed: false }),
      );
  }, [pathname, requireLicense, licenseKey]);

  return state;
}
