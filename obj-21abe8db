import React, { useState } from "react";
import { View, Text, TextInput, TouchableOpacity, StyleSheet, Alert } from "react-native";
import { useAuthStore } from "../stores/authStore";

export default function LicenseEntryScreen({ onActivated }: { onActivated: () => void }) {
  const { validateLicense, license } = useAuthStore();
  const [licenseKey, setLicenseKey] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async () => {
    if (!licenseKey.trim()) {
      Alert.alert("Error", "Enter a license key");
      return;
    }
    setLoading(true);
    try {
      await validateLicense(licenseKey.trim());
      onActivated();
    } catch (e) {
      const msg = e instanceof Error ? e.message : "License validation failed";
      Alert.alert("Error", msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Pharmacy Mobile</Text>
      <Text style={styles.subtitle}>Enter your license key to activate</Text>
      <TextInput
        style={styles.input}
        placeholder="XXXX-XXXX-XXXX-XXXX"
        placeholderTextColor="#666"
        value={licenseKey}
        onChangeText={setLicenseKey}
        autoCapitalize="characters"
      />
      <TouchableOpacity style={styles.btn} onPress={handleSubmit} disabled={loading || license.loading}>
        <Text style={styles.btnText}>{loading ? "Activating..." : "Activate"}</Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#000", justifyContent: "center", padding: 24 },
  title: { color: "#fff", fontSize: 32, fontWeight: "bold", marginBottom: 8, textAlign: "center" },
  subtitle: { color: "#888", fontSize: 16, marginBottom: 32, textAlign: "center" },
  input: {
    backgroundColor: "#222",
    color: "#fff",
    padding: 16,
    borderRadius: 12,
    fontSize: 18,
    textAlign: "center",
    marginBottom: 24,
  },
  btn: {
    backgroundColor: "#007AFF",
    paddingVertical: 16,
    borderRadius: 12,
    alignItems: "center",
  },
  btnText: { color: "#fff", fontWeight: "bold", fontSize: 18 },
});
