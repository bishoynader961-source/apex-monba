import React, { useEffect, useState } from "react";
import { View, Text, TouchableOpacity, FlatList, TextInput, StyleSheet, Alert } from "react-native";
import { useInventoryStore } from "../stores/inventoryStore";
import { formatMoney, parseMoney } from "../lib/decimalCurrency";

export default function InventoryScreen() {
  const { products, loading, loadProducts, search, filters, setFilters } = useInventoryStore();
  const [searchQuery, setSearchQuery] = useState("");

  useEffect(() => {
    if (!products.length && !loading) {
      loadProducts();
    }
  }, [loadProducts, products.length, loading]);

  const handleSearch = (text: string) => {
    setSearchQuery(text);
    if (text.length >= 2) {
      search(text);
    }
  };

  const renderItem = ({ item }: { item: typeof products[0] }) => (
    <TouchableOpacity style={styles.item}>
      <View style={styles.itemInfo}>
        <Text style={styles.itemName}>{item.name}</Text>
        <Text style={styles.itemBarcode}>{item.internal_unique_barcode}</Text>
        <Text style={styles.itemVendor}>Vendor: {item.vendor_name}</Text>
        {item.expiry_date && (
          <Text style={styles.itemExpiry}>Expires: {item.expiry_date}</Text>
        )}
      </View>
      <View style={styles.itemPrice}>
        <Text style={styles.priceText}>{formatMoney(parseMoney(item.price))}</Text>
        {item.reorder_threshold && item.reorder_threshold > 0 && (
          <Text style={styles.lowStockBadge}>Low stock</Text>
        )}
      </View>
    </TouchableOpacity>
  );

  return (
    <View style={styles.container}>
      <View style={styles.searchBar}>
        <TextInput
          style={styles.searchInput}
          placeholder="Search by name or barcode..."
          placeholderTextColor="#888"
          value={searchQuery}
          onChangeText={handleSearch}
        />
      </View>
      {loading ? (
        <Text style={styles.loading}>Loading...</Text>
      ) : (
        <FlatList
          data={products}
          keyExtractor={(item) => String(item.id)}
          renderItem={renderItem}
          contentContainerStyle={styles.list}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#000" },
  searchBar: {
    padding: 12,
    borderBottomWidth: 1,
    borderBottomColor: "#333",
    backgroundColor: "#1a1a1a",
  },
  searchInput: {
    backgroundColor: "#222",
    color: "#fff",
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 6,
  },
  list: { paddingBottom: 20 },
  loading: { color: "#888", textAlign: "center", padding: 20 },
  item: {
    flexDirection: "row",
    justifyContent: "space-between",
    padding: 16,
    borderBottomWidth: 1,
    borderBottomColor: "#222",
  },
  itemInfo: { flex: 3 },
  itemName: { color: "#fff", fontSize: 16, fontWeight: "bold" },
  itemBarcode: { color: "#888", fontSize: 12, marginTop: 2 },
  itemVendor: { color: "#888", fontSize: 12, marginTop: 2 },
  itemExpiry: { color: "#FF9500", fontSize: 12, marginTop: 2 },
  itemPrice: { flex: 1, alignItems: "flex-end" },
  priceText: { color: "#34C759", fontSize: 16, fontWeight: "bold" },
  lowStockBadge: {
    color: "#FF3B30",
    fontSize: 10,
    marginTop: 4,
    backgroundColor: "#222211",
    paddingHorizontal: 4,
    borderRadius: 2,
  },
});
