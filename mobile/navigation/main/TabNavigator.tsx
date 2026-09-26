import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import React from "react";
import { StyleSheet, Text, View } from "react-native";
import POSScreen from "../../screens/POSScreen";
import InventoryScreen from "../../screens/InventoryScreen";
import InventoryScannerScreen from "../../screens/InventoryScannerScreen";
import ReceivingScreen from "../../screens/ReceivingScreen";
import ShiftsScreen from "../../screens/ShiftsScreen";
import AnalyticsScreen from "../../screens/AnalyticsScreen";
import RxQueueScreen from "../../screens/RxQueueScreen";
import SettingsScreen from "../../screens/SettingsScreen";
import PatientSearchScreen from "../../screens/PatientSearchScreen";
import { useOfflineQueueStore } from "../../stores/offlineQueue";

export type TabParamList = {
  POS: undefined;
  Inventory: undefined;
  Scanner: undefined;
  Receiving: undefined;
  Shifts: undefined;
  Analytics: undefined;
  RxQueue: undefined;
  Patients: undefined;
  Settings: undefined;
};

const Tab = createBottomTabNavigator<TabParamList>();

function TabBarLabel({ title }: { title: string }) {
  return <Text style={{ fontSize: 12, marginBottom: 4 }}>{title}</Text>;
}

// Step 1.8: POS tab carries the pending-sync badge ("X pending sync"). No
// indicator when the queue is empty; dead sales turn the badge red.
function PosTabLabel() {
  const pending = useOfflineQueueStore((s) => s.pendingCount);
  const dead = useOfflineQueueStore((s) => s.deadCount);
  const total = pending + dead;
  return (
    <View style={styles.labelWrap}>
      <Text style={{ fontSize: 12, marginBottom: 4 }}>POS</Text>
      {total > 0 && (
        <View style={[styles.badge, dead > 0 && styles.badgeDead]}>
          <Text style={styles.badgeText}>
            {dead > 0 ? `${total}!` : `${total} pending sync`}
          </Text>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  labelWrap: { alignItems: "center" },
  badge: {
    backgroundColor: "#007AFF",
    borderRadius: 8,
    paddingHorizontal: 6,
    paddingVertical: 1,
    marginBottom: 2,
  },
  badgeDead: { backgroundColor: "#FF3B30" },
  badgeText: { color: "#fff", fontSize: 10, fontWeight: "bold" },
});

export default function MainTabNavigator() {
  return (
    <Tab.Navigator
      screenOptions={({ route }) => ({
        headerShown: false,
        tabBarIcon: () => (
          <View style={{ width: 24, height: 2, backgroundColor: "#007AFF" }} />
        ),
        tabBarLabel: () =>
          route.name === "POS" ? <PosTabLabel /> : <TabBarLabel title={route.name} />,
      })}
    >
      <Tab.Screen name="POS" component={POSScreen} />
      <Tab.Screen name="Inventory" component={InventoryScreen} />
      <Tab.Screen name="Scanner" component={InventoryScannerScreen} />
      <Tab.Screen name="Receiving" component={ReceivingScreen} />
      <Tab.Screen name="Shifts" component={ShiftsScreen} />
      <Tab.Screen name="Analytics" component={AnalyticsScreen} />
      <Tab.Screen name="RxQueue" component={RxQueueScreen} />
      <Tab.Screen name="Patients" component={PatientSearchScreen} />
      <Tab.Screen name="Settings" component={SettingsScreen} />
    </Tab.Navigator>
  );
}
