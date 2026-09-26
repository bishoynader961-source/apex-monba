import React, { useEffect, useState } from "react";
import { View, Text, TouchableOpacity, StyleSheet, Alert } from "react-native";
import { useAuthStore } from "../stores/authStore";
import { getStoredDeviceId, getDeviceName } from "../lib/deviceId";
import { readCrashLog } from "../lib/diagnostics/classifier";
import { RecoveryActions } from "./MobileRecoveryScreen";

export default function SettingsScreen() {
  const {
    user,
    logout,
    license,
    biometricsEnabled,
    enableBiometrics,
    disableBiometrics,
    timeouts,
  } = useAuthStore();
  const [deviceId, setDeviceId] = useState<string | null>(null);
  const [deviceName, setDeviceName] = useState<string>("");
  const [licenseStatus, setLicenseStatus] = useState<string>("");

  useEffect(() => {
    getStoredDeviceId().then(setDeviceId);
    setDeviceName(getDeviceName());
    setLicenseStatus(license.status);
  }, [license.status]);

  const handleLogout = async () => {
    Alert.alert("Confirm", "Log out?", [
      { text: "Cancel", style: "cancel" },
      {
        text: "Log Out",
        style: "destructive",
        onPress: async () => {
          await logout();
        },
      },
    ]);
  };

  const [crashCount, setCrashCount] = useState(0);
  const [showSupport, setShowSupport] = useState(false);
  useEffect(() => {
    void readCrashLog().then((log) => setCrashCount(log.length));
  }, []);

  // Step 1.3: biometric unlock preference. Enabling requires a successful
  // hardware prompt; failing hardware/enrollment surfaces as an alert.
  const toggleBiometrics = async () => {
    try {
      if (biometricsEnabled) {
        await disableBiometrics();
      } else {
        await enableBiometrics();
      }
    } catch (e) {
      Alert.alert("Biometrics", e instanceof Error ? e.message : "Not available on this device.");
    }
  };

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Settings</Text>

      {user && (
        <View style={styles.section}>
          <Text style={styles.label}>User</Text>
          <Text style={styles.value}>{user.username}</Text>
          <Text style={styles.label}>Role</Text>
          <Text style={styles.value}>{user.role ?? "—"}</Text>
        </View>
      )}

      <View style={styles.section}>
        <Text style={styles.label}>License</Text>
        <Text style={styles.value}>{licenseStatus.toUpperCase()}</Text>
        {license.expiresAt && (
          <>
            <Text style={styles.label}>Expires</Text>
            <Text style={styles.value}>{new Date(license.expiresAt).toLocaleDateString()}</Text>
          </>
        )}
      </View>

      <View style={styles.section}>
        <Text style={styles.label}>Device Name</Text>
        <Text style={styles.value}>{deviceName}</Text>
        {deviceId && (
          <>
            <Text style={styles.label}>Device ID</Text>
            <Text style={styles.value}>{deviceId}</Text>
          </>
        )}
      </View>

      {/* Step 1.3: session security (mirrors desktop sessionStore limits) */}
      <View style={styles.section}>
        <Text style={styles.label}>Security</Text>
        <Text style={styles.value}>
          Session limits: {timeouts.idleMinutes} min idle / {timeouts.absoluteMinutes} min absolute
        </Text>
        <TouchableOpacity style={styles.recoveryToggle} onPress={toggleBiometrics}>
          <Text style={{ color: biometricsEnabled ? "#34C759" : "#9ca3af", fontSize: 13 }}>
            {biometricsEnabled
              ? "● Biometric unlock ON — tap to disable"
              : "Enable biometric unlock (Face ID / fingerprint)"}
          </Text>
        </TouchableOpacity>
      </View>

      {/* Step 3.7: Support & Recovery (blueprint Point 3) */}
      <View style={styles.section}>
        <Text style={styles.label}>Support &amp; Recovery</Text>
        <TouchableOpacity
          style={styles.recoveryToggle}
          onPress={() => setShowSupport((v: boolean) => !v)}
        >
          <Text style={{ color: crashCount > 0 ? '#f87171' : '#9ca3af', fontSize: 13 }}>
            {crashCount > 0 ? `● ${crashCount} recent issue${crashCount === 1 ? '' : 's'} — tap for help` : 'Get help / diagnostics'}
          </Text>
        </TouchableOpacity>
        {showSupport && <RecoveryActions />}
      </View>

      <TouchableOpacity style={styles.logoutBtn} onPress={handleLogout}>
        <Text style={styles.logoutText}>Logout</Text>
      </TouchableOpacity>
    </View>
  );
}


const styles = StyleSheet.create({
  recoveryToggle: { paddingVertical: 6 },

  container: { flex: 1, backgroundColor: "#000", padding: 16 },
  title: { color: "#fff", fontSize: 24, fontWeight: "bold", marginBottom: 16 },
  section: {
    backgroundColor: "#1a1a1a",
    padding: 16,
    borderRadius: 12,
    marginBottom: 16,
    gap: 8,
  },
  label: { color: "#888", fontSize: 12, textTransform: "uppercase" },
  value: { color: "#fff", fontSize: 16 },
  logoutBtn: {
    backgroundColor: "#FF3B30",
    paddingVertical: 12,
    borderRadius: 8,
    alignItems: "center",
  },
  logoutText: { color: "#fff", fontWeight: "bold", fontSize: 16 },
});
