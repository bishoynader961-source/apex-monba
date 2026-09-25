import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import React from "react";
import { Text, View } from "react-native";
import POSScreen from "../../screens/POSScreen";
import InventoryScreen from "../../screens/InventoryScreen";
import InventoryScannerScreen from "../../screens/InventoryScannerScreen";
import ReceivingScreen from "../../screens/ReceivingScreen";
import ShiftsScreen from "../../screens/ShiftsScreen";
import AnalyticsScreen from "../../screens/AnalyticsScreen";
import RxQueueScreen from "../../screens/RxQueueScreen";
import SettingsScreen from "../../screens/SettingsScreen";

export type TabParamList = {
  POS: undefined;
  Inventory: undefined;
  Scanner: undefined;
  Receiving: undefined;
  Shifts: undefined;
  Analytics: undefined;
  RxQueue: undefined;
  Settings: undefined;
};

const Tab = createBottomTabNavigator<TabParamList>();

function TabBarLabel({ title }: { title: string }) {
  return <Text style={{ fontSize: 12, marginBottom: 4 }}>{title}</Text>;
}

export default function MainTabNavigator() {
  return (
    <Tab.Navigator
      screenOptions={({ route }) => ({
        headerShown: false,
        tabBarIcon: () => (
          <View style={{ width: 24, height: 2, backgroundColor: "#007AFF" }} />
        ),
        tabBarLabel: () => <TabBarLabel title={route.name} />,
      })}
    >
      <Tab.Screen name="POS" component={POSScreen} />
      <Tab.Screen name="Inventory" component={InventoryScreen} />
      <Tab.Screen name="Scanner" component={InventoryScannerScreen} />
      <Tab.Screen name="Receiving" component={ReceivingScreen} />
      <Tab.Screen name="Shifts" component={ShiftsScreen} />
      <Tab.Screen name="Analytics" component={AnalyticsScreen} />
      <Tab.Screen name="RxQueue" component={RxQueueScreen} />
      <Tab.Screen name="Settings" component={SettingsScreen} />
    </Tab.Navigator>
  );
}
