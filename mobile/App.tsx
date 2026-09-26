import React, { useEffect, useRef } from "react";
import { StatusBar } from "expo-status-bar";
import { Alert } from "react-native";
import { AppState } from "react-native";
import RootNavigator from "./navigation/RootNavigator";
import { useSync } from "./lib/hooks/useSync";
import { useAuthStore } from "./stores/authStore";
import { usePosStore } from "./stores/posStore";
import LicenseEntryScreen from "./screens/LicenseEntryScreen";
import { ErrorBoundary } from "./components/ErrorBoundary";
import {
  setActivityCallback,
  setForbiddenCallback,
  setUnauthorizedCallback,
} from "./lib/api/client";

export default function App() {
  useSync();
  const { initialized, license, checkLicense } = useAuthStore();
  const { hydrated: posHydrated, hydrate: hydratePos } = usePosStore();

  useEffect(() => {
    if (!initialized) {
      useAuthStore.getState().initialize();
    }
    if (!posHydrated) {
      hydratePos();
    }
  }, [initialized, posHydrated, hydratePos]);

  // Step 1.3: session-security wiring.
  //  * 401-after-failed-refresh → tear the local session down (→ Login screen
  //    via RootNavigator). The user guard prevents an interceptor↔logout loop:
  //    api.logout() itself 401s once the session is already gone.
  //  * 403 → permission alert, never a crash.
  //  * successful responses feed the idle-timeout clock.
  //  * a 30s watcher enforces idle + absolute session limits (same minute
  //    values as desktop, loaded from SystemSetting in initialize()).
  useEffect(() => {
    setUnauthorizedCallback(() => {
      const s = useAuthStore.getState();
      if (s.user) void s.logout();
    });
    setForbiddenCallback(() => {
      Alert.alert("Permission denied", "Your account does not have access to that feature.");
    });
    setActivityCallback(() => useAuthStore.getState().noteActivity());
    const stopWatch = useAuthStore.getState().startSessionWatch(30_000);
    return () => {
      setUnauthorizedCallback(null);
      setForbiddenCallback(null);
      setActivityCallback(null);
      stopWatch();
    };
  }, []);

  // Step 1.3: returning to the foreground re-validates the live session via
  // biometrics instead of silently resuming (only when the user enabled it).
  const appState = useRef(AppState.currentState);
  useEffect(() => {
    const sub = AppState.addEventListener("change", (next) => {
      if (appState.current.match(/inactive|background/) && next === "active") {
        void useAuthStore.getState().unlockWithBiometrics();
      }
      appState.current = next;
    });
    return () => sub.remove();
  }, []);

  if (!initialized || license.loading) {
    return null;
  }

  if (license.status === "no_license") {
    return (
      <>
        <StatusBar style="light" />
        <LicenseEntryScreen onActivated={checkLicense} />
      </>
    );
  }

  return (
    <>
      <StatusBar style="light" />
      <ErrorBoundary><RootNavigator /></ErrorBoundary>
    </>
  );
}
