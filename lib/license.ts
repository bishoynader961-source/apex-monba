import crypto from "crypto";
import redis from "./redis";

interface LicenseRecord {
  key: string;
  email: string;
  gateway: "paddle";
  status: "active";
  activated_device_id: string | null;
  created_at: string;
}

export function generateLicenseKey(): string {
  const hash = crypto.createHash("sha256").update(crypto.randomUUID()).digest("hex");
  return `PPRO-${hash.slice(0, 4).toUpperCase()}-${hash.slice(4, 8).toUpperCase()}-${hash.slice(8, 12).toUpperCase()}`;
}

export async function createLicense(
  email: string,
  gateway: "paddle"
): Promise<LicenseRecord> {
  const key = generateLicenseKey();

  const record: LicenseRecord = {
    key,
    email,
    gateway,
    status: "active",
    activated_device_id: null,
    created_at: new Date().toISOString(),
  };

  // Store by license key (primary lookup)
  await redis.set(`license:${key}`, JSON.stringify(record));

  // Store email→key mapping (lookup by email)
  await redis.set(`email:${email}:license`, key);

  return record;
}

export async function getLicenseByKey(key: string): Promise<LicenseRecord | null> {
  const raw = await redis.get<string>(`license:${key}`);
  if (!raw) return null;
  return typeof raw === "string" ? JSON.parse(raw) : raw;
}

export async function getLicenseByEmail(email: string): Promise<LicenseRecord | null> {
  const key = await redis.get<string>(`email:${email}:license`);
  if (!key) return null;
  return getLicenseByKey(key);
}
