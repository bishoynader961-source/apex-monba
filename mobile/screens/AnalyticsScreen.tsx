import React, { useState, useCallback, useEffect } from "react";
import { View, Text, TouchableOpacity, FlatList, StyleSheet, Alert } from "react-native";
import * as analyticsApi from "../lib/api/analytics";
import { parseMoney, formatMoney } from "../lib/decimalCurrency";
import { useAuthStore } from "../stores/authStore";
import type { DemandAnalyticsItem, TopSellingItem } from "../types/contracts";

const PERIODS: Array<{ label: string; value: "day" | "week" | "month" }> = [
  { label: "Day", value: "day" },
  { label: "Week", value: "week" },
  { label: "Month", value: "month" },
];

export default function AnalyticsScreen() {
  const { user } = useAuthStore();
  const isOwner = user?.role_id === 1;

  const [activeTab, setActiveTab] = useState<"top-selling" | "demand">("top-selling");
  const [period, setPeriod] = useState<"day" | "week" | "month">("month");
  const [topSelling, setTopSelling] = useState<TopSellingItem[]>([]);
  const [demandItems, setDemandItems] = useState<DemandAnalyticsItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [windowStart, setWindowStart] = useState<string>("");
  const [windowEnd, setWindowEnd] = useState<string>("");
  const [totalRevenue, setTotalRevenue] = useState<string>("");

  // Check permission on mount
  useEffect(() => {
    if (!isOwner) {
      Alert.alert("Access Denied", "Analytics dashboard is restricted to owners only.");
    }
  }, [isOwner]);

  if (!isOwner) {
    return (
      <View style={styles.container}>
        <Text style={styles.title}>Analytics</Text>
        <View style={styles.accessDenied}>
          <Text style={styles.accessText}>🔒 Owner Access Required</Text>
          <Text style={styles.accessSubtext}>
            This dashboard is restricted to pharmacy owners.
          </Text>
        </View>
      </View>
    );
  }

  const loadTopSelling = useCallback(async () => {
    setLoading(true);
    try {
      const res = await analyticsApi.getTopSelling(period);
      setTopSelling(res.items);
      setWindowStart(res.window_start);
      setWindowEnd(res.window_end);
      setTotalRevenue("0");
      setDemandItems([]);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed to load analytics";
      Alert.alert("Error", msg);
    } finally {
      setLoading(false);
    }
  }, [period]);

  const loadDemand = useCallback(async () => {
    setLoading(true);
    try {
      const res = await analyticsApi.getDemandAnalytics({ sort_by: "total_revenue" });
      setDemandItems(res.items);
      setWindowStart(res.window_start);
      setWindowEnd(res.window_end);
      setTotalRevenue(formatMoney(parseMoney(res.total_revenue)));
      setTopSelling([]);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed to load analytics";
      Alert.alert("Error", msg);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleTabChange = (tab: "top-selling" | "demand") => {
    setActiveTab(tab);
    if (tab === "top-selling") {
      loadTopSelling();
    } else {
      loadDemand();
    }
  };

  const handlePeriodChange = (p: "day" | "week" | "month") => {
    setPeriod(p);
    if (activeTab === "top-selling") {
      loadTopSelling();
    }
  };

  React.useEffect(() => {
    loadTopSelling();
  }, [loadTopSelling]);

  const renderTopSellingItem = ({ item }: { item: TopSellingItem }) => (
    <View style={styles.itemRow}>
      <Text style={styles.itemRank}>#{item.rank}</Text>
      <Text style={styles.itemName}>{item.product_name}</Text>
      <Text style={styles.itemQty}>Qty: {item.total_quantity}</Text>
      <Text style={styles.itemRev}>{formatMoney(parseMoney(item.total_revenue))}</Text>
    </View>
  );

  const renderDemandItem = ({ item }: { item: DemandAnalyticsItem }) => {
    const bg = {
      FAST_MOVING: "#30B054",
      MODERATE_MOVING: "#007AFF",
      SLOW_MOVING: "#FF9500",
      NON_MOVING: "#888",
    }[item.velocity_category] || "#888";

    return (
      <View style={styles.itemRow}>
        <Text style={styles.itemName}>{item.product_name}</Text>
        <View style={[styles.badge, { backgroundColor: bg }]}>
          <Text style={styles.badgeText}>{item.velocity_category}</Text>
        </View>
        <Text style={styles.itemQty}>Demand: {item.total_quantity_demanded}</Text>
        <Text style={styles.itemRev}>Revenue: {formatMoney(parseMoney(item.total_revenue))}</Text>
      </View>
    );
  };

  const renderPeriodBtn = (p: "day" | "week" | "month") => (
    <TouchableOpacity
      key={p}
      style={[styles.periodBtn, period === p && styles.periodBtnActive]}
      onPress={() => handlePeriodChange(p)}
    >
      <Text style={[styles.periodText, period === p && styles.periodTextActive]}>
        {PERIODS.find((x) => x.value === p)?.label}
      </Text>
    </TouchableOpacity>
  );

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Analytics</Text>
      <Text style={styles.window}>
        {windowStart} → {windowEnd}
      </Text>

      <View style={styles.tabBar}>
        <TouchableOpacity
          style={[styles.tabBtn, activeTab === "top-selling" && styles.tabBtnActive]}
          onPress={() => handleTabChange("top-selling")}
        >
          <Text style={styles.tabText}>Top Selling</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.tabBtn, activeTab === "demand" && styles.tabBtnActive]}
          onPress={() => handleTabChange("demand")}
        >
          <Text style={styles.tabText}>Demand Velocity</Text>
        </TouchableOpacity>
      </View>

      {activeTab === "top-selling" ? (
        <View style={styles.periodRow}>{PERIODS.map((p) => renderPeriodBtn(p.value))}</View>
      ) : null}

      {loading ? (
        <Text style={styles.loading}>Loading...</Text>
      ) : activeTab === "top-selling" ? (
        <FlatList
          data={topSelling}
          keyExtractor={(item) => item.rank.toString()}
          renderItem={renderTopSellingItem}
          style={styles.list}
        />
      ) : (
        <FlatList
          data={demandItems}
          keyExtractor={(item) => item.product_name}
          renderItem={renderDemandItem}
          style={styles.list}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#000", padding: 16 },
  title: { color: "#fff", fontSize: 24, fontWeight: "bold", marginBottom: 8 },
  window: { color: "#888", fontSize: 13, marginBottom: 16 },
  tabBar: { flexDirection: "row", marginBottom: 12, gap: 8 },
  tabBtn: { flex: 1, paddingVertical: 10, borderRadius: 8, backgroundColor: "#222", alignItems: "center" },
  tabBtnActive: { backgroundColor: "#007AFF" },
  tabText: { color: "#fff", fontWeight: "bold", fontSize: 15 },
  periodRow: { flexDirection: "row", marginBottom: 12, gap: 8, justifyContent: "center" },
  periodBtn: { paddingHorizontal: 16, paddingVertical: 8, borderRadius: 6, backgroundColor: "#222" },
  periodBtnActive: { backgroundColor: "#007AFF" },
  periodText: { color: "#aaa", fontSize: 14 },
  periodTextActive: { color: "#fff", fontWeight: "bold" },
  list: { flex: 1 },
  itemRow: {
    padding: 12,
    borderBottomColor: "#333",
    borderBottomWidth: 1,
    gap: 4,
  },
  itemRank: { color: "#888", fontSize: 14 },
  itemName: { color: "#fff", fontSize: 16 },
  itemQty: { color: "#aaa", fontSize: 14 },
  itemRev: { color: "#aaa", fontSize: 14 },
  badge: { alignSelf: "flex-start", paddingHorizontal: 8, paddingVertical: 2, borderRadius: 4, marginTop: 4 },
  badgeText: { color: "#fff", fontSize: 11, fontWeight: "bold" },
  loading: { color: "#aaa", fontSize: 16, textAlign: "center", marginTop: 32 },
  accessDenied: { flex: 1, justifyContent: "center", alignItems: "center", marginTop: 60 },
  accessText: { color: "#FF3B30", fontSize: 22, fontWeight: "bold", marginBottom: 12 },
  accessSubtext: { color: "#888", fontSize: 16, textAlign: "center", paddingHorizontal: 32 },
});
