import { NavigationContainer } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import React, { useEffect } from "react";
import { useAuthStore } from "../stores/authStore";
import LoginScreen from "./auth/LoginScreen";
import MainTabNavigator from "./main/TabNavigator";
import { usePosStore } from "../stores/posStore";

export type RootStackParamList = {
  Login: undefined;
  Main: undefined;
};

const Stack = createNativeStackNavigator<RootStackParamList>();

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
      <Stack.Navigator screenOptions={{ headerShown: false }}>
        {user ? (
          <Stack.Screen name="Main" component={MainTabNavigator} />
        ) : (
          <Stack.Screen name="Login" component={LoginScreen} />
        )}
      </Stack.Navigator>
    </NavigationContainer>
  );
}
