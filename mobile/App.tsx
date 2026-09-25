import React, { useEffect } from "react";
import { StatusBar } from "expo-status-bar";
import RootNavigator from "./navigation/RootNavigator";
import { useSync } from "./lib/hooks/useSync";
import { useAuthStore } from "./stores/authStore";
import { usePosStore } from "./stores/posStore";
import LicenseEntryScreen from "./screens/LicenseEntryScreen";

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
      <RootNavigator />
    </>
  );
}
