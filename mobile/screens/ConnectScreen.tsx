/**
 * Step 1.7 (blueprint §1.4.3/§1.4.4): QR pairing screen.
 *
 * Shown by RootNavigator whenever no desktop base URL is resolved (fresh
 * install, or the cached desktop stopped answering — §1.3.3). The user scans
 * the QR from the desktop Mobile Access tab:
 *   1. Client checks (per owner decision, 2026-09-26): the JSON parses and
 *      expiresAt is a sane ISO timestamp. NO client-side HMAC — the server
 *      verifies the signature (CHECK A) at POST /api/v1/auth/mobile-register.
 *   2. The RAW parsed payload is forwarded verbatim as `qr_payload`, so the
 *      server validates the HMAC over exactly the bytes the QR carried.
 *   3. On success: url → SecureStore `ph_desktop_url`, one-time device_token
 *      → SecureStore `ph_device_token`, then the connection gate flips and
 *      RootNavigator shows the normal login screen.
 *
 * Security/UX invariants: failures surface as friendly messages only (no
 * signatures, statuses, or URLs of failed requests); no credentials are ever
 * logged; the pairing POST uses raw axios against the scanned origin because
 * the shared client cannot resolve a base URL before pairing exists.
 */
import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Platform,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import { CameraView, useCameraPermissions } from "expo-camera";
import * as Device from "expo-device";
import axios from "axios";

import type { MobileRegisterResponse } from "../types/contracts";
import { desktopOrigin, storeDesktopUrl } from "../lib/api/baseUrl";
import { storeDeviceToken } from "../lib/api/client";
import { getStoredDeviceId } from "../lib/deviceId";
import { useConnectionStore } from "../stores/connectionStore";

type ConnectStatus = "scanning" | "validating" | "pairing" | "paired" | "error";

/** Shape of the desktop QR (camelCase, exactly as the desktop serializes it). */
interface ScannedQrPayload {
  url?: unknown;
  networkKey?: unknown;
  instanceId?: unknown;
  apiVersion?: unknown;
  expiresAt?: unknown;
}

function parseQr(raw: string): ScannedQrPayload | null {
  try {
    const parsed: unknown = JSON.parse(raw);
    if (parsed !== null && typeof parsed === "object") {
      return parsed as ScannedQrPayload;
    }
    return null;
  } catch {
    return null;
  }
}

/** Basic sanity only (not enforcement) — the server enforces the real expiry. */
function hasSaneExpiry(qr: ScannedQrPayload): boolean {
  return (
    typeof qr.expiresAt === "string" &&
    qr.expiresAt.length > 0 &&
    !Number.isNaN(Date.parse(qr.expiresAt))
  );
}

function isScannedQrComplete(qr: ScannedQrPayload): boolean {
  return (
    typeof qr.url === "string" &&
    qr.url.startsWith("http") &&
    typeof qr.networkKey === "string" &&
    qr.networkKey.length > 0 &&
    typeof qr.instanceId === "string" &&
    qr.instanceId.length > 0
  );
}

function hostOf(url: string): string {
  try {
    return new URL(url).hostname;
  } catch {
    return url;
  }
}

export default function ConnectScreen() {
  const [permission, requestPermission] = useCameraPermissions();
  const [status, setStatus] = useState<ConnectStatus>("scanning");
  const [connectingTo, setConnectingTo] = useState<string | null>(null);
  const rescanTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    // Clean up any pending auto-rescan so we never setState after unmount.
    return () => {
      if (rescanTimer.current) clearTimeout(rescanTimer.current);
    };
  }, []);

  const scheduleRescan = useCallback(() => {
    if (rescanTimer.current) clearTimeout(rescanTimer.current);
    rescanTimer.current = setTimeout(() => setStatus("scanning"), 1800);
  }, []);

  const handleBarcode = useCallback(
    async (event: { data: string }) => {
      setStatus("validating");
      const qr = parseQr(event.data);

      if (qr === null || !isScannedQrComplete(qr)) {
        Alert.alert(
          "Not a pairing code",
          "That QR code isn't a Pharmacy Suite pairing code. Open Mobile Access on the desktop and scan the code shown there.",
        );
        setStatus("error");
        scheduleRescan();
        return;
      }
      if (!hasSaneExpiry(qr)) {
        Alert.alert(
          "Damaged pairing code",
          "This pairing code can't be read. Generate a new one on the desktop (Mobile Access → Refresh QR) and scan again.",
        );
        setStatus("error");
        scheduleRescan();
        return;
      }

      // The QR is structurally valid — hand the RAW payload to the server.
      const url = qr.url as string;
      const origin = desktopOrigin(url);
      setConnectingTo(hostOf(origin));
      setStatus("pairing");
      try {
        const deviceId = await getStoredDeviceId();
        const deviceName = `${Platform.OS} ${Device.modelName ?? "device"}`;
        const resp = await axios.post<MobileRegisterResponse>(
          `${origin}/api/v1/auth/mobile-register`,
          {
            device_id: deviceId,
            device_name: deviceName,
            qr_payload: qr, // verbatim scan — server verifies the HMAC over it
          },
          { timeout: 15000 },
        );
        const token = resp.data?.device_token;
        if (typeof token !== "string" || token.length === 0) {
          throw new Error("missing device token");
        }

        // Success: persist identity, then flip the connection gate. Both the
        // URL and the one-time token live in SecureStore (Keychain/Keystore).
        await storeDeviceToken(token);
        await storeDesktopUrl(origin);
        // resolveBaseUrl re-reads the just-stored URL, pings the desktop and
        // publishes mobileBaseUrl — RootNavigator immediately shows Login.
        await useConnectionStore.getState().resolveBaseUrl();
        setStatus("paired");
      } catch (err) {
        setStatus("error");
        setConnectingTo(null);
        // Friendly messages only — no statuses, signatures, or URLs. The
        // three causes a user can act on: wrong network, desktop mode,
        // expired/rejected code.
        const unreachable = axios.isAxiosError(err) && !err.response;
        const disabled = axios.isAxiosError(err) && err.response?.status === 403;
        Alert.alert(
          "Pairing failed",
          unreachable
            ? "We couldn't reach the pharmacy computer. Make sure this phone and the desktop are on the same Wi-Fi network, then scan a fresh QR code."
            : disabled
              ? "Mobile access is currently turned off on the desktop. Ask the admin to set Mobile Access mode to Shared, then scan again."
              : "The desktop rejected this pairing code — it may have expired. Generate a fresh one (Mobile Access → Refresh QR) and scan again.",
        );
        scheduleRescan();
      }
    },
    [scheduleRescan],
  );

  if (!permission) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color="#007AFF" />
        <Text style={styles.message}>Preparing camera…</Text>
      </View>
    );
  }

  if (!permission.granted) {
    return (
      <View style={styles.centered}>
        <Text style={styles.title}>Connect to Pharmacy Suite</Text>
        <Text style={styles.message}>
          Camera access is needed to scan the pairing code shown on the
          pharmacy computer.
        </Text>
        <TouchableOpacity style={styles.primaryBtn} onPress={requestPermission}>
          <Text style={styles.primaryBtnText}>Allow camera</Text>
        </TouchableOpacity>
      </View>
    );
  }

  const busy = status === "validating" || status === "pairing";

  return (
    <View style={styles.container}>
      <CameraView
        style={StyleSheet.absoluteFill}
        // Only accept frames while idle — one QR, one pairing attempt.
        onBarcodeScanned={status === "scanning" ? handleBarcode : undefined}
        barcodeScannerSettings={{ barcodeTypes: ["qr"] }}
      />
      <View style={styles.overlay}>
        <Text style={styles.title}>Connect to Pharmacy Suite</Text>
        <Text style={styles.message}>
          Scan the QR code from the desktop Mobile Access screen to pair this
          phone with your pharmacy computer.
        </Text>
        {busy && (
          <View style={styles.statusBox}>
            <ActivityIndicator color="#fff" />
            <Text style={styles.statusText}>
              {status === "pairing" && connectingTo
                ? `Pairing with ${connectingTo}…`
                : "Checking pairing code…"}
            </Text>
          </View>
        )}
        {status === "paired" && (
          <View style={styles.statusBox}>
            <Text style={styles.statusText}>Paired — opening sign-in…</Text>
          </View>
        )}
        {status === "error" && (
          <Text style={styles.statusText}>Scan again when ready…</Text>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#000" },
  centered: {
    flex: 1,
    backgroundColor: "#000",
    alignItems: "center",
    justifyContent: "center",
    padding: 24,
    gap: 12,
  },
  overlay: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.55)",
    alignItems: "center",
    justifyContent: "center",
    padding: 24,
    gap: 12,
  },
  title: { color: "#fff", fontSize: 22, fontWeight: "bold", textAlign: "center" },
  message: { color: "#d1d5db", fontSize: 15, textAlign: "center", lineHeight: 22 },
  statusBox: {
    backgroundColor: "rgba(0,0,0,0.7)",
    borderRadius: 12,
    padding: 12,
    alignItems: "center",
    gap: 8,
  },
  statusText: { color: "#fff", fontSize: 14, textAlign: "center" },
  primaryBtn: {
    backgroundColor: "#007AFF",
    paddingVertical: 12,
    paddingHorizontal: 24,
    borderRadius: 8,
  },
  primaryBtnText: { color: "#fff", fontWeight: "bold", fontSize: 16 },
});
