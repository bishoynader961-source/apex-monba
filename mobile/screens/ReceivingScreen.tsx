import React, { useState, useEffect, useCallback } from "react";
import { View, Text, TouchableOpacity, TextInput, FlatList, StyleSheet, Alert } from "react-native";
import { usePosStore } from "../stores/posStore";
import * as receivingApi from "../lib/api/receiving";
import { formatMoney, parseMoney } from "../lib/decimalCurrency";
import type { PurchaseOrderRead, PurchaseOrderCreate, PurchaseOrderItemCreate, PurchaseOrderReceiveItem, ReceivingLogRead } from "../types/contracts";

interface ScannedItem {
  product_name: string;
  quantity: number;
  unit_price: string;
  lot_number?: string;
  expiry_date?: string;
}

export default function ReceivingScreen() {
  const { error: posError } = usePosStore();
  const [activeTab, setActiveTab] = useState<"create" | "log">("create");
  const [vendorName, setVendorName] = useState("");
  const [items, setItems] = useState<ScannedItem[]>([]);
  const [productName, setProductName] = useState("");
  const [quantity, setQuantity] = useState("1");
  const [unitPrice, setUnitPrice] = useState("");
  const [receivingLog, setReceivingLog] = useState<ReceivingLogRead[]>([]);
  const [loading, setLoading] = useState(false);

  const loadLog = useCallback(async () => {
    try {
      const res = await receivingApi.listReceivingLog();
      setReceivingLog(res.items);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed to load receiving log";
      Alert.alert("Error", msg);
    }
  }, []);

  useEffect(() => {
    loadLog();
  }, [loadLog]);

  const addItem = () => {
    if (!productName || !quantity || !unitPrice) {
      Alert.alert("Error", "Enter product name, quantity, and unit price");
      return;
    }
    const newItem: ScannedItem = {
      product_name: productName,
      quantity: parseInt(quantity, 10),
      unit_price: unitPrice,
    };
    setItems([...items, newItem]);
    setProductName("");
    setQuantity("1");
    setUnitPrice("");
  };

  const createPO = async () => {
    if (!vendorName || items.length === 0) {
      Alert.alert("Error", "Enter a vendor name and add at least one item");
      return;
    }
    setLoading(true);
    try {
        const payload: PurchaseOrderCreate = {
          vendor_name: vendorName,
          items: items.map((i) => ({
            product_name: i.product_name,
            quantity: i.quantity,
            unit_price: formatMoney(parseMoney(i.unit_price)),
          })),
        };
      await receivingApi.createPurchaseOrder(payload);
      Alert.alert("Success", `PO created for ${vendorName}`);
      setVendorName("");
      setItems([]);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed to create PO";
      Alert.alert("Error", msg);
    } finally {
      setLoading(false);
    }
  };

  const renderItem = ({ item }: { item: ScannedItem }) => (
    <View style={styles.itemRow}>
      <Text style={styles.itemText}>{item.product_name}</Text>
      <Text style={styles.itemMeta}>Qty: {item.quantity}</Text>
      <Text style={styles.itemMeta}>{formatMoney(parseMoney(item.unit_price))}</Text>
    </View>
  );

  const renderLogItem = ({ item }: { item: ReceivingLogRead }) => (
    <View style={styles.logRow}>
      <Text style={styles.logProduct}>{item.product_name}</Text>
      <Text style={styles.logMeta}>{item.vendor_name}</Text>
      <Text style={styles.logMeta}>Qty: {item.quantity}</Text>
      <Text style={styles.logMeta}>{formatMoney(parseMoney(item.total_cost))}</Text>
      <Text style={styles.logMeta}>{item.date_received}</Text>
      {item.lot_number ? <Text style={styles.logMeta}>Lot: {item.lot_number}</Text> : null}
    </View>
  );

  if (posError) {
    return (
      <View style={styles.container}>
        <Text style={styles.errorText}>{posError}</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={styles.tabBar}>
        <TouchableOpacity
          style={[styles.tabBtn, activeTab === "create" && styles.tabBtnActive]}
          onPress={() => setActiveTab("create")}
        >
          <Text style={styles.tabText}>New PO</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.tabBtn, activeTab === "log" && styles.tabBtnActive]}
          onPress={() => setActiveTab("log")}
        >
          <Text style={styles.tabText}>Receiving Log</Text>
        </TouchableOpacity>
      </View>
      {activeTab === "create" ? (
        <>
          <Text style={styles.title}>New Purchase Order</Text>
          <Text style={styles.label}>Vendor Name</Text>
          <TextInput
            style={styles.input}
            placeholder="Vendor name"
            placeholderTextColor="#666"
            value={vendorName}
            onChangeText={setVendorName}
          />
          <Text style={styles.label}>Product Name</Text>
          <TextInput
            style={styles.input}
            placeholder="Product name"
            placeholderTextColor="#666"
            value={productName}
            onChangeText={setProductName}
          />
          <Text style={styles.label}>Quantity</Text>
          <TextInput
            style={styles.input}
            placeholder="1"
            placeholderTextColor="#666"
            keyboardType="numeric"
            value={quantity}
            onChangeText={setQuantity}
          />
          <Text style={styles.label}>Unit Price</Text>
          <TextInput
            style={styles.input}
            placeholder="0.00"
            placeholderTextColor="#666"
            keyboardType="numeric"
            value={unitPrice}
            onChangeText={setUnitPrice}
          />
          <TouchableOpacity style={styles.btn} onPress={addItem} disabled={loading}>
            <Text style={styles.btnText}>Add Item</Text>
          </TouchableOpacity>
          {items.length > 0 ? (
            <FlatList
              data={items}
              keyExtractor={(_, idx) => idx.toString()}
              renderItem={renderItem}
              style={styles.list}
            />
          ) : null}
          <TouchableOpacity
            style={[styles.btn, styles.createBtn, { opacity: loading ? 0.5 : 1 }]}
            onPress={createPO}
            disabled={loading}
          >
            <Text style={styles.btnText}>{loading ? "Creating..." : "Create PO"}</Text>
          </TouchableOpacity>
        </>
      ) : (
        <>
          <Text style={styles.title}>Receiving Log</Text>
          <FlatList
            data={receivingLog}
            keyExtractor={(item) => item.id.toString()}
            renderItem={renderLogItem}
            style={styles.list}
          />
        </>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#000", padding: 16 },
  tabBar: { flexDirection: "row", marginBottom: 16, gap: 8 },
  tabBtn: { flex: 1, paddingVertical: 10, borderRadius: 8, backgroundColor: "#222", alignItems: "center" },
  tabBtnActive: { backgroundColor: "#007AFF" },
  tabText: { color: "#fff", fontWeight: "bold", fontSize: 15 },
  title: { color: "#fff", fontSize: 24, fontWeight: "bold", marginBottom: 16 },
  label: { color: "#aaa", fontSize: 14, marginBottom: 4, marginTop: 8 },
  input: {
    backgroundColor: "#222",
    color: "#fff",
    padding: 12,
    borderRadius: 8,
    fontSize: 16,
  },
  btn: {
    backgroundColor: "#007AFF",
    paddingVertical: 12,
    borderRadius: 8,
    alignItems: "center",
    marginTop: 8,
  },
  createBtn: { backgroundColor: "#30B054" },
  btnText: { color: "#fff", fontWeight: "bold", fontSize: 16 },
  list: { marginTop: 16 },
  itemRow: {
    padding: 12,
    borderBottomColor: "#333",
    borderBottomWidth: 1,
  },
  itemText: { color: "#fff", fontSize: 16 },
  itemMeta: { color: "#aaa", fontSize: 14 },
  logRow: {
    padding: 12,
    borderBottomColor: "#333",
    borderBottomWidth: 1,
  },
  logProduct: { color: "#fff", fontSize: 16, fontWeight: "bold" },
  logMeta: { color: "#aaa", fontSize: 14 },
  errorText: { color: "#ff4444", fontSize: 16 },
});
