import React, { useEffect, useState, useCallback } from "react";
import { View, Text, FlatList, StyleSheet, ActivityIndicator, RefreshControl, TouchableOpacity } from "react-native";
import * as rxQueueApi from "../lib/api/rxQueue";
import type { RxQueueItem, RxQueueCounts, RxQueueFilters } from "../types/contracts";

const STATUS_COLORS: Record<string, string> = {
  Pending: "#FF9500",
  Billed: "#007AFF",
  Verified: "#5856D6",
  Filled: "#34C759",
  "Will Call": "#AF52DE",
  Rejected: "#FF3B30",
};

export default function RxQueueScreen() {
  const [items, setItems] = useState<RxQueueItem[]>([]);
  const [counts, setCounts] = useState<RxQueueCounts>({ processing: 0, rejects: 0, ready: 0 });
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [filter, setFilter] = useState<RxQueueFilters>({ page: 1, page_size: 50 });
  const [activeTab, setActiveTab] = useState<"all" | "processing" | "rejects" | "ready">("all");

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [queueRes, countsRes] = await Promise.all([
        rxQueueApi.getRxQueue(filter),
        rxQueueApi.getRxQueueCounts(),
      ]);
      setItems(queueRes.items);
      setCounts(countsRes);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed to load Rx queue";
      console.error(msg);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [filter]);

  const onRefresh = useCallback(() => {
    setRefreshing(true);
    loadData();
  }, [loadData]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const filteredItems = items.filter((item) => {
    if (activeTab === "all") return true;
    if (activeTab === "processing") return ["Pending", "Billed", "Verified"].includes(item.status);
    if (activeTab === "rejects") return item.status === "Rejected";
    if (activeTab === "ready") return ["Filled", "Will Call"].includes(item.status);
    return true;
  });

  const tabCounts = {
    all: items.length,
    processing: counts.processing,
    rejects: counts.rejects,
    ready: counts.ready,
  };

  const renderItem = ({ item }: { item: RxQueueItem }) => {
    const statusColor = STATUS_COLORS[item.status] || "#888";
    return (
      <TouchableOpacity style={styles.item}>
        <View style={styles.itemLeft}>
          <Text style={styles.itemRxNumber}>RX #{item.rx_number ?? item.id}</Text>
          <Text style={styles.itemPatient}>{item.patient_name}</Text>
          <Text style={styles.itemDrug}>{item.product_name}</Text>
          <Text style={styles.itemDetails}>
            Qty: {item.quantity} | Refills: {item.refill_count}/{item.refills_authorized}
          </Text>
        </View>
        <View style={styles.itemRight}>
          <View style={[styles.statusBadge, { backgroundColor: statusColor }]}>
            <Text style={styles.statusText}>{item.status}</Text>
          </View>
          <Text style={styles.itemDate}>{item.fill_date}</Text>
        </View>
      </TouchableOpacity>
    );
  };

  const renderTab = (label: string, key: "all" | "processing" | "rejects" | "ready") => (
    <TouchableOpacity
      style={[
        styles.tab,
        activeTab === key && styles.tabActive,
        key === "rejects" && tabCounts.rejects > 0 && styles.tabAlert,
      ]}
      onPress={() => setActiveTab(key)}
    >
      <Text style={[styles.tabText, activeTab === key && styles.tabTextActive]}>{label}</Text>
      <Text style={[styles.tabCount, activeTab === key && styles.tabCountActive]}>{tabCounts[key]}</Text>
    </TouchableOpacity>
  );

  if (loading && !items.length) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color="#007AFF" />
        <Text style={styles.loadingText}>Loading prescriptions...</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>Rx Queue</Text>
      </View>

      <View style={styles.tabBar}>
        {renderTab("All", "all")}
        {renderTab("Processing", "processing")}
        {renderTab("Rejects", "rejects")}
        {renderTab("Ready", "ready")}
      </View>

      <FlatList
        data={filteredItems}
        keyExtractor={(item) => String(item.id)}
        renderItem={renderItem}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} colors={["#007AFF"]} />
        }
        contentContainerStyle={styles.list}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Text style={styles.emptyText}>No prescriptions in this view</Text>
          </View>
        }
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#000" },
  header: { padding: 16, borderBottomWidth: 1, borderBottomColor: "#222" },
  title: { color: "#fff", fontSize: 24, fontWeight: "bold" },
  tabBar: { flexDirection: "row", paddingHorizontal: 12, paddingVertical: 8, gap: 6 },
  tab: {
    flex: 1,
    flexDirection: "row",
    justifyContent: "center",
    alignItems: "center",
    gap: 6,
    paddingVertical: 10,
    borderRadius: 8,
    backgroundColor: "#1a1a1a",
    borderWidth: 1,
    borderColor: "#333",
  },
  tabActive: { backgroundColor: "#007AFF", borderColor: "#007AFF" },
  tabAlert: { borderColor: "#FF3B30" },
  tabText: { color: "#aaa", fontSize: 12, fontWeight: "600" },
  tabTextActive: { color: "#fff" },
  tabCount: { color: "#666", fontSize: 11, fontWeight: "bold" },
  tabCountActive: { color: "#fff" },
  list: { padding: 12, paddingBottom: 100 },
  item: {
    flexDirection: "row",
    justifyContent: "space-between",
    backgroundColor: "#1a1a1a",
    borderRadius: 10,
    padding: 14,
    marginBottom: 10,
    borderWidth: 1,
    borderColor: "#222",
  },
  itemLeft: { flex: 1 },
  itemRight: { alignItems: "flex-end", minWidth: 100 },
  itemRxNumber: { color: "#fff", fontSize: 16, fontWeight: "bold", marginBottom: 4 },
  itemPatient: { color: "#ccc", fontSize: 14, marginBottom: 2 },
  itemDrug: { color: "#007AFF", fontSize: 13, marginBottom: 2 },
  itemDetails: { color: "#888", fontSize: 11 },
  itemDate: { color: "#666", fontSize: 11, marginTop: 4 },
  statusBadge: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 12 },
  statusText: { color: "#fff", fontSize: 11, fontWeight: "bold" },
  empty: { flex: 1, justifyContent: "center", alignItems: "center", padding: 40 },
  emptyText: { color: "#666", fontSize: 16 },
  centered: { flex: 1, justifyContent: "center", alignItems: "center", gap: 12 },
  loadingText: { color: "#888", fontSize: 14 },
});