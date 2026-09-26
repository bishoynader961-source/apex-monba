import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  RefreshControl,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import * as patientsApi from "../lib/api/patients";
import type { PatientRead } from "../types/contracts";

const PAGE_SIZE = 50;

function displayName(p: PatientRead): string {
  const name =
    [p.last_name, p.first_name].filter(Boolean).join(", ") || p.name || `Patient #${p.id}`;
  return name;
}

/**
 * Step 1.1b — Patient Search (read-only, P0 parity gap).
 * Search + detail view over the live /api/v1/patients endpoints. No patient
 * data is stored locally or cached: every result list and every detail card
 * is fetched on demand and kept only in component state.
 */
export default function PatientSearchScreen() {
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<PatientRead[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<PatientRead | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const fetchPage = useCallback(async (q: string, nextPage: number, append: boolean) => {
    setLoading(true);
    setError(null);
    try {
      const res = await patientsApi.listPatients({ q: q || undefined, page: nextPage, page_size: PAGE_SIZE });
      setItems((prev) => (append ? [...prev, ...res.items] : res.items));
      setTotal(res.total);
      setPage(nextPage);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load patients");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  // Debounced live search — every keystroke re-queries the server; nothing is
  // written to AsyncStorage (PHI never touches disk on mobile v1).
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      void fetchPage(query.trim(), 1, false);
    }, 350);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query, fetchPage]);

  const onRefresh = useCallback(() => {
    setRefreshing(true);
    void fetchPage(query.trim(), 1, false);
  }, [query, fetchPage]);

  const openDetail = useCallback(async (id: number) => {
    setDetailLoading(true);
    setSelected(null);
    try {
      // Full record is re-fetched live when opened — never served from cache.
      setSelected(await patientsApi.getPatient(id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load patient");
    } finally {
      setDetailLoading(false);
    }
  }, []);

  const renderRow = ({ item }: { item: PatientRead }) => (
    <TouchableOpacity style={styles.item} onPress={() => void openDetail(item.id)}>
      <View style={styles.itemLeft}>
        <Text style={styles.itemName}>{displayName(item)}</Text>
        <Text style={styles.itemMeta}>
          DOB {item.dob || "—"} · {item.contact_phone || item.cell_phone || "no phone"}
        </Text>
        <Text style={styles.itemMeta}>
          {item.insurance_provider || "Self-pay"}
          {item.patient_allergies ? ` · ⚠ ${item.patient_allergies}` : ""}
        </Text>
      </View>
      <Text style={styles.itemId}>#{item.id}</Text>
    </TouchableOpacity>
  );

  const detailField = (label: string, value?: string | null) => (
    <View key={label} style={styles.detailRow}>
      <Text style={styles.detailLabel}>{label}</Text>
      <Text style={styles.detailValue}>{value || "—"}</Text>
    </View>
  );

  const hasMore = items.length < total;

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Patients</Text>
      <TextInput
        style={styles.search}
        placeholder="Search by name, phone, license…"
        placeholderTextColor="#666"
        value={query}
        onChangeText={setQuery}
        autoCapitalize="none"
        autoCorrect={false}
      />

      {error && <Text style={styles.error}>{error}</Text>}
      {detailLoading && <ActivityIndicator color="#007AFF" style={styles.detailSpinner} />}

      <FlatList
        data={items}
        keyExtractor={(item) => String(item.id)}
        renderItem={renderRow}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} colors={["#007AFF"]} />}
        contentContainerStyle={styles.list}
        ListEmptyComponent={
          !loading ? (
            <View style={styles.empty}>
              <Text style={styles.emptyText}>
                {query.trim() ? "No patients match this search" : "Type to search patients"}
              </Text>
            </View>
          ) : null
        }
        ListFooterComponent={
          hasMore && !loading ? (
            <TouchableOpacity style={styles.moreBtn} onPress={() => void fetchPage(query.trim(), page + 1, true)}>
              <Text style={styles.moreText}>Load more ({total - items.length} remaining)</Text>
            </TouchableOpacity>
          ) : null
        }
      />

      {selected && (
        <View style={styles.detailOverlay}>
          <View style={styles.detailCard}>
            <View style={styles.detailHeader}>
              <Text style={styles.detailTitle}>{displayName(selected)}</Text>
              <TouchableOpacity onPress={() => setSelected(null)}>
                <Text style={styles.detailClose}>✕</Text>
              </TouchableOpacity>
            </View>
            {detailField("Patient ID", `#${selected.id}`)}
            {detailField("Date of birth", selected.dob)}
            {detailField("Sex", selected.sex)}
            {detailField("Contact phone", selected.contact_phone)}
            {detailField("Cell phone", selected.cell_phone)}
            {detailField("Email", selected.email)}
            {detailField("Address", [selected.address, selected.city, selected.state, selected.zip].filter(Boolean).join(", ") || null)}
            {detailField("Driver license", selected.driver_license)}
            {detailField("Insurance", selected.insurance_provider)}
            {detailField("Policy #", selected.policy_number)}
            {detailField("Group #", selected.group_number)}
            {detailField("Allergies", selected.patient_allergies)}
            {detailField("Comments", selected.comments)}
            <Text style={styles.detailNote}>Read-only view — editing is desktop-only in v1.</Text>
          </View>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#000" },
  title: { color: "#fff", fontSize: 24, fontWeight: "bold", padding: 16, paddingBottom: 8 },
  search: {
    backgroundColor: "#1a1a1a",
    color: "#fff",
    marginHorizontal: 16,
    marginBottom: 8,
    paddingHorizontal: 14,
    paddingVertical: 12,
    borderRadius: 8,
    fontSize: 16,
    borderWidth: 1,
    borderColor: "#333",
  },
  error: { color: "#FF3B30", fontSize: 13, paddingHorizontal: 16, paddingBottom: 6 },
  detailSpinner: { marginVertical: 8 },
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
  itemId: { color: "#666", fontSize: 12, marginLeft: 8 },
  itemName: { color: "#fff", fontSize: 16, fontWeight: "bold", marginBottom: 4 },
  itemMeta: { color: "#888", fontSize: 12, marginBottom: 2 },
  empty: { flex: 1, justifyContent: "center", alignItems: "center", padding: 40 },
  emptyText: { color: "#666", fontSize: 16 },
  moreBtn: { alignItems: "center", padding: 14, marginBottom: 10 },
  moreText: { color: "#007AFF", fontSize: 14, fontWeight: "600" },
  detailOverlay: {
    position: "absolute" as const,
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: "rgba(0,0,0,0.75)",
    justifyContent: "center",
    padding: 16,
  },
  detailCard: {
    backgroundColor: "#1a1a1a",
    borderRadius: 14,
    borderWidth: 1,
    borderColor: "#333",
    padding: 16,
    maxHeight: "85%",
  },
  detailHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 10,
  },
  detailTitle: { color: "#fff", fontSize: 20, fontWeight: "bold", flex: 1 },
  detailClose: { color: "#888", fontSize: 20, paddingLeft: 12 },
  detailRow: { paddingVertical: 5, borderBottomWidth: 1, borderBottomColor: "#222" },
  detailLabel: { color: "#888", fontSize: 11, textTransform: "uppercase" },
  detailValue: { color: "#fff", fontSize: 15 },
  detailNote: { color: "#666", fontSize: 12, marginTop: 10 },
});
