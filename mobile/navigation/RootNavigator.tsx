import { NavigationContainer } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import React, { useEffect } from "react";
import { useAuthStore } from "../stores/authStore";
import LoginScreen from "./auth/LoginScreen";
import MainTabNavigator from "./main/TabNavigator";
import { usePosStore } from "../stores/posStore";
import ConnectScreen from "../screens/ConnectScreen";
import { useConnectionStore } from "../stores/connectionStore";

export type RootStackParamList = {
  Login: undefined;
  Main: undefined;
};

const Stack = createNativeStackNavigator<RootStackParamList>();

/**
 * Step 1.7 (blueprint §1.3.3): the pairing gate. Until a desktop origin is
 * resolved (SecureStore ph_desktop_url answered the health ping), the entire
 * navigator is replaced by ConnectScreen — nothing can call the API before
 * the app is paired. Reactive: pairing (or Settings → Reconnect) flips
 * mobileBaseUrl and this re-renders into the normal flow instantly.
 */
function PairGate({ children }: { children: React.ReactNode }) {
  const paired = useConnectionStore((s) => s.mobileBaseUrl !== null);

  useEffect(() => {
    if (!paired) {
      // Existing installs: resolve once on mount. Failure is expected on a
      // fresh install (that's exactly the ConnectScreen case) — the gate
      // stays up and the sentinel rejection is swallowed here.
      useConnectionStore.getState().resolveBaseUrl().catch(() => {});
    }
  }, [paired]);

  if (!paired) {
    return <ConnectScreen />;
  }
  return <>{children}</>;
}

export default function RootNavigator() {
  const { user, initialized, initialize } = useAuthStore();
  const { hydrated: posHydrated, hydrate: hydratePos } = usePosStore();

  useEffect(() => {
    if (!initialized) {
      initialize();
    }
    if (!posHydrated) {
      hydratePos();
    }
  }, [initialized, initialize, posHydrated, hydratePos]);

  if (!initialized) {
    return null;
  }

  return (
    <NavigationContainer>
      <PairGate>
        <Stack.Navigator screenOptions={{ headerShown: false }}>
          {user ? (
            <Stack.Screen name="Main" component={MainTabNavigator} />
          ) : (
            <Stack.Screen name="Login" component={LoginScreen} />
          )}
        </Stack.Navigator>
      </PairGate>
    </NavigationContainer>
  );
}
