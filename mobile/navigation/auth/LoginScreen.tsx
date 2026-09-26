import React, { useState } from "react";
import { View, Text, TextInput, TouchableOpacity, StyleSheet, Alert, StatusBar } from "react-native";
import { useAuthStore } from "../../stores/authStore";

export default function LoginScreen({ navigation }: any) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [unlocking, setUnlocking] = useState(false);
  const { login, biometricsEnabled, unlockWithBiometrics } = useAuthStore();

  const handleLogin = async () => {
    if (!username || !password) {
      Alert.alert("Error", "Please enter username and password");
      return;
    }
    setLoading(true);
    try {
      await login(username, password);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Login failed";
      Alert.alert("Login Failed", msg);
    } finally {
      setLoading(false);
    }
  };

  // Step 1.3: biometric unlock resumes an existing SecureStore session; it
  // can never create one. No live session → fall back to the password form.
  const handleBiometricUnlock = async () => {
    setUnlocking(true);
    try {
      const ok = await unlockWithBiometrics();
      if (!ok) {
        Alert.alert("Unlock unavailable", "No active session to unlock — please sign in with your password.");
      }
    } catch (e) {
      Alert.alert("Unlock failed", e instanceof Error ? e.message : "Please try again.");
    } finally {
      setUnlocking(false);
    }
  };

  return (
    <View style={styles.container}>
      <StatusBar barStyle="light-content" backgroundColor="#000" />
      <View style={styles.form}>
        <Text style={styles.title}>Pharmacy POS</Text>
        <Text style={styles.subtitle}>Mobile Login</Text>

        <View style={styles.inputGroup}>
          <Text style={styles.label}>Username</Text>
          <TextInput
            style={styles.input}
            placeholder="Enter username"
            placeholderTextColor="#666"
            value={username}
            onChangeText={setUsername}
            autoCapitalize="none"
            onSubmitEditing={() => {}}
          />
        </View>

        <View style={styles.inputGroup}>
          <Text style={styles.label}>Password</Text>
          <TextInput
            style={styles.input}
            placeholder="Enter password"
            placeholderTextColor="#666"
            value={password}
            onChangeText={setPassword}
            secureTextEntry
            onSubmitEditing={handleLogin}
          />
        </View>

        <TouchableOpacity
          style={[styles.loginBtn, loading && styles.loginBtnDisabled]}
          onPress={handleLogin}
          disabled={loading}
        >
          <Text style={styles.loginBtnText}>
            {loading ? "Signing in..." : "Sign In"}
          </Text>
        </TouchableOpacity>

        {biometricsEnabled && (
          <TouchableOpacity
            style={[styles.biometricBtn, unlocking && styles.loginBtnDisabled]}
            onPress={handleBiometricUnlock}
            disabled={unlocking || loading}
          >
            <Text style={styles.biometricText}>
              {unlocking ? "Waiting for biometrics…" : "🔓 Unlock with biometrics"}
            </Text>
          </TouchableOpacity>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#000",
    justifyContent: "center",
    alignItems: "center",
  },
  form: {
    width: "85%",
    gap: 20,
  },
  title: {
    color: "#fff",
    fontSize: 32,
    fontWeight: "bold",
    textAlign: "center",
  },
  subtitle: {
    color: "#888",
    fontSize: 16,
    textAlign: "center",
    marginBottom: 20,
  },
  inputGroup: {
    gap: 6,
  },
  label: {
    color: "#aaa",
    fontSize: 13,
    fontWeight: "600",
  },
  input: {
    backgroundColor: "#1a1a1a",
    color: "#fff",
    paddingHorizontal: 14,
    paddingVertical: 12,
    borderRadius: 8,
    fontSize: 16,
    borderWidth: 1,
    borderColor: "#333",
  },
  loginBtn: {
    backgroundColor: "#007AFF",
    paddingVertical: 14,
    borderRadius: 8,
    alignItems: "center",
    marginTop: 10,
  },
  loginBtnDisabled: {
    backgroundColor: "#333",
  },
  biometricBtn: {
    paddingVertical: 12,
    borderRadius: 8,
    alignItems: "center",
    borderWidth: 1,
    borderColor: "#007AFF",
  },
  biometricText: {
    color: "#007AFF",
    fontSize: 14,
    fontWeight: "600",
  },
  loginBtnText: {
    color: "#fff",
    fontSize: 16,
    fontWeight: "bold",
  },
});
