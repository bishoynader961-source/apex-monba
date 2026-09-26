// ── Mobile Recovery Screen (Blueprint Task 3, Steps 3.4 + 3.7) ───────────────
// SECURITY:
//   * Shows ONLY classified codes/messages from classifier.ts and the fixed
//     messages returned by fixEngine.ts. Raw error text is never rendered
//     (invariant #7).
//   * Sharing uses the React Native Share API exclusively (invariant #6):
//     the report is built from the crash log (codes + metadata only) and the
//     user picks the channel — no SMTP, no silent network sends.
//   * The fix-code input feeds applyMobileFix(); results render as the
//     engine's fixed messages. Nothing about the code is echoed or stored.

import React, { useCallback, useEffect, useState } from "react";
import {
  ScrollView,
  Share,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import Constants from "expo-constants";
import {
  classifyError,
  clearCrashLog,
  messageForCode,
  readCrashLog,
  type CrashLogEntry,
} from "../lib/diagnostics/classifier";
import { applyMobileFix } from "../lib/security/fixEngine";
import { getHealthSnapshot, probeHealth } from "../lib/api/health";

const SUPPORT_EMAIL = "pharmacypro.support@gmail.com";

export function MobileRecoveryScreen({
  code,
  category,
}: {
  code: string;
  category: string;
}) {
  const message = messageForCode(code);
  return (
    <View style={styles.container}>
      <Text style={styles.icon}>⚠️</Text>
      <Text style={styles.title}>Pharmacy Suite</Text>
      <Text style={styles.code}>{code}</Text>
      <Text style={styles.message}>{message}</Text>
      <RecoveryActions errorCode={code} category={category} />
    </View>
  );
}

/**
 * Full recovery surface. Rendered by the error boundary on a crash, and
 * reachable from Settings → Support for proactive diagnostics.
 */
export function RecoveryActions({
  errorCode,
  category,
}: {
  errorCode?: string;
  category?: string;
}) {
  const [crashLog, setCrashLog] = useState<CrashLogEntry[]>([]);
  const [fixCode, setFixCode] = useState("");
  const [fixResult, setFixResult] = useState<{ ok: boolean; text: string } | null>(null);
  const [health, setHealth] = useState(getHealthSnapshot());

  useEffect(() => {
    void readCrashLog().then(setCrashLog);
    const stop = startHealthPollingSafe();
    return stop;
  }, []);

  useEffect(() => {
    const off = onHealthSafe(setHealth);
    return off;
  }, []);

  const handleProbe = useCallback(async () => {
    await probeHealth();
  }, []);

  const handleShare = useCallback(async () => {
    const version = Constants.expoConfig?.version ?? "unknown";
    const lines: string[] = [
      "=== PharmacySuite Diagnostic Report ===",
      `Generated: ${new Date().toISOString()}`,
      `App Version: ${version}`,
      `Connection: ${health.state}`,
      "Crash log (classified codes only — no patient data):",
    ];
    if (crashLog.length === 0) lines.push("  (none)");
    for (const entry of crashLog) {
      lines.push(`  [${entry.timestamp}] ${entry.code} (${entry.category})`);
    }
    lines.push("=== End of Report ===");
    try {
      await Share.share({ title: "Pharmacy Suite Diagnostic Report", message: lines.join("\n") });
    } catch {
      // User cancelled the share sheet — nothing to do.
    }
  }, [crashLog, health.state]);

  const handleAutoFix = useCallback(async () => {
    if (errorCode === "ERR_SESSION_EXPIRED" || category === "auth") {
      // The API client clears tokens on real auth failures; here we just
      // advise the user — auto-clearing here would violate the offline guard.
      setFixResult({ ok: true, text: "Please log in again from the home screen." });
      return;
    }
    if (errorCode === "ERR_NO_CONNECTION" || category === "network") {
      await handleProbe();
      setFixResult({
        ok: getHealthSnapshot().state === "healthy",
        text: getHealthSnapshot().state === "healthy"
          ? "Connection restored."
          : "Still offline. Check WiFi, then Reconnect to Desktop.",
      });
      return;
    }
    setFixResult({ ok: false, text: "No automatic fix for this error. Contact support." });
  }, [errorCode, category, handleProbe]);

  const handleApplyFix = useCallback(async () => {
    if (!fixCode.trim()) {
      setFixResult({ ok: false, text: "Paste the fix code first." });
      return;
    }
    const result = await applyMobileFix(fixCode.trim());
    setFixResult({ ok: result.ok, text: result.message });
    if (result.ok) {
      await clearCrashLog();
      void readCrashLog().then(setCrashLog);
    }
  }, [fixCode]);

  return (
    <ScrollView style={styles.sheet} contentContainerStyle={styles.sheetContent}>
      <View style={styles.actions}>
        <Text style={styles.sectionTitle}>Automatic repair</Text>
        <TouchableOpacity style={styles.button} onPress={() => void handleAutoFix()}>
          <Text style={styles.buttonText}>Try automatic fix</Text>
        </TouchableOpacity>

        <Text style={styles.sectionTitle}>Diagnostics</Text>
        <TouchableOpacity style={styles.button} onPress={() => void handleShare()}>
          <Text style={styles.buttonText}>Share Diagnostic Info</Text>
        </TouchableOpacity>
        <Text style={styles.hint}>
          Contains app version, connection state, and error codes only. You choose where to send it.
        </Text>

        <Text style={styles.sectionTitle}>Apply fix code</Text>
        <TextInput
          style={styles.input}
          multiline
          placeholder="Paste the fix code from support…"
          value={fixCode}
          onChangeText={setFixCode}
          autoCapitalize="none"
          autoCorrect={false}
        />
        <TouchableOpacity style={styles.button} onPress={() => void handleApplyFix()}>
          <Text style={styles.buttonText}>Apply Fix</Text>
        </TouchableOpacity>
        {fixResult && (
          <Text style={fixResult.ok ? styles.okText : styles.errText}>{fixResult.text}</Text>
        )}

        <Text style={styles.sectionTitle}>Connection</Text>
        <Text style={styles.hint}>Server state: {health.state}</Text>
        <TouchableOpacity style={styles.button} onPress={() => void handleProbe()}>
          <Text style={styles.buttonText}>Check connection now</Text>
        </TouchableOpacity>

        <Text style={styles.sectionTitle}>Support</Text>
        <Text style={styles.hint}>{SUPPORT_EMAIL}</Text>
        <Text style={styles.hint}>
          🔒 Support will never ask for your password or PIN.
        </Text>

        {crashLog.length > 0 && (
          <View>
            <Text style={styles.sectionTitle}>Recent error codes</Text>
            {crashLog.slice().reverse().map((entry, index) => (
              <Text key={`${entry.timestamp}-${index}`} style={styles.logLine}>
                [{entry.timestamp.slice(0, 19).replace("T", " ")}] {entry.code}
              </Text>
            ))}
          </View>
        )}
      </View>
    </ScrollView>
  );
}

// Imported late to avoid a require cycle with the polling module.
import { startHealthPolling, onHealthChange } from "../lib/api/health";
function startHealthPollingSafe(): () => void {
  return startHealthPolling(60_000);
}
function onHealthSafe(fn: (s: ReturnType<typeof getHealthSnapshot>) => void): () => void {
  return onHealthChange(fn);
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0f0f23", alignItems: "center", justifyContent: "center", padding: 24 },
  sheet: { flex: 1, backgroundColor: "#0f0f23" },
  sheetContent: { padding: 20, paddingBottom: 48 },
  icon: { fontSize: 48, marginBottom: 12 },
  title: { color: "#e0e0e0", fontSize: 20, fontWeight: "600", marginBottom: 4 },
  code: { color: "#f87171", fontSize: 16, fontWeight: "700", marginBottom: 8 },
  message: { color: "#c7c7d1", fontSize: 14, textAlign: "center", marginBottom: 16 },
  actions: { width: "100%" },
  sectionTitle: { color: "#a5b4fc", fontSize: 13, fontWeight: "600", marginTop: 18, marginBottom: 6 },
  button: { backgroundColor: "#4f46e5", borderRadius: 8, paddingVertical: 12, paddingHorizontal: 16, marginVertical: 4 },
  buttonText: { color: "#fff", fontSize: 14, fontWeight: "600", textAlign: "center" },
  hint: { color: "#9ca3af", fontSize: 12, marginBottom: 6 },
  input: { backgroundColor: "#0d0d20", borderColor: "#4b5563", borderWidth: 1, borderRadius: 8, color: "#e5e7eb", minHeight: 80, padding: 10, marginBottom: 6, textAlignVertical: "top" },
  okText: { color: "#4ade80", fontSize: 13, marginTop: 4 },
  errText: { color: "#f87171", fontSize: 13, marginTop: 4 },
  logLine: { color: "#9ca3af", fontSize: 11, fontFamily: undefined },
});
