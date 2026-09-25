import React, { useState } from "react";
import { View, Text, TouchableOpacity, FlatList, StyleSheet, Alert, ScrollView } from "react-native";
import { usePosStore } from "../stores/posStore";
import { formatMoney, parseMoney, mulByQty, sumMoney } from "../lib/decimalCurrency";
import { ProductRead } from "../types/contracts";
import * as inventoryApi from "../lib/api/inventory";
import BarcodeScannerModal from "../components/BarcodeScanner";

export default function POSScreen() {
  const [scannerVisible, setScannerVisible] = useState(false);
  const [discountInput, setDiscountInput] = useState("");
  const [drawerReason, setDrawerReason] = useState("");

  const {
    lines,
    addLine,
    updateQty,
    remove,
    clear,
    checkout,
    result,
    error,
    offlineCount,
    currentShiftId,
    syncing,
    setDiscount,
    clearDiscount,
    toggleTaxExempt,
    setPayments,
    flushQueue,
  } = usePosStore();

  const subtotal = sumMoney(
    lines.map((l) => mulByQty(parseMoney(l.unit_price), l.quantity)),
  );

  const handleCheckout = async () => {
    await checkout("Cash");
  };

  const handleFlush = async () => {
    await flushQueue();
    if (error) Alert.alert("Sync", error);
  };

  const handleScan = (barcode: string) => {
    setScannerVisible(false);
    inventoryApi
      .getProductByBarcode(barcode)
      .then((product) => {
        addLine({
          product_name: product.name,
          quantity: 1,
          unit_price: product.price,
        });
      })
      .catch((e) => {
        const msg = e instanceof Error ? e.message : "Product not found";
        Alert.alert("Scan Error", msg);
      });
  };

  if (!currentShiftId) {
    return (
      <View style={styles.centered}>
        <Text style={styles.title}>No Active Shift</Text>
        <Text style={styles.subtitle}>Open a shift to start selling</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>POS — Shift #{currentShiftId}</Text>
        {offlineCount > 0 && (
          <TouchableOpacity onPress={handleFlush} disabled={syncing}>
            <Text style={styles.syncBadge}>
              {syncing ? "Syncing..." : `${offlineCount} offline`}
            </Text>
          </TouchableOpacity>
        )}
      </View>

      <ScrollView style={styles.cartSection}>
        {lines?.length === 0 ? (
          <Text style={styles.empty}>Scan a product to start</Text>
        ) : (
          lines.map((line, i) => (
            <View key={line.product_name} style={styles.cartItem}>
              <Text style={styles.cartItemName}>{line.product_name}</Text>
              <View style={styles.cartItemRow}>
                <Text style={styles.cartItemPrice}>
                  {formatMoney(parseMoney(line.unit_price))}
                </Text>
                <TouchableOpacity
                  style={styles.qtyButton}
                  onPress={() => updateQty(line.product_name, -1)}
                >
                  <Text>-</Text>
                </TouchableOpacity>
                <Text style={styles.qty}>{line.quantity}</Text>
                <TouchableOpacity
                  style={styles.qtyButton}
                  onPress={() => updateQty(line.product_name, 1)}
                >
                  <Text>+</Text>
                </TouchableOpacity>
                <TouchableOpacity onPress={() => remove(line.product_name)}>
                  <Text style={styles.removeBtn}>✕</Text>
                </TouchableOpacity>
              </View>
            </View>
          ))
        )}
      </ScrollView>

      <View style={styles.totals}>
        <View style={styles.totalRow}>
          <Text style={styles.totalLabel}>Subtotal</Text>
          <Text style={styles.totalValue}>{formatMoney(subtotal)}</Text>
        </View>
      </View>

      <View style={styles.actions}>
        <TouchableOpacity
          style={styles.actionBtnSecondary}
          onPress={() => setScannerVisible(true)}
        >
          <Text style={styles.actionBtnTextSecondary}>Scan</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.actionBtnSecondary} onPress={clear}>
          <Text style={styles.actionBtnTextSecondary}>Clear</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.actionBtn, lines?.length === 0 && styles.actionBtnDisabled]}
          onPress={handleCheckout}
          disabled={lines?.length === 0}
        >
          <Text style={styles.actionBtnText}>Checkout ${formatMoney(subtotal)}</Text>
        </TouchableOpacity>
      </View>

      {error && <Text style={styles.error}>{error}</Text>}
      {result && (
        <View style={styles.resultBanner}>
          <Text style={styles.resultText}>
            Receipt #{result.receipt_number} — ${formatMoney(parseMoney(result.total_amount))}
          </Text>
        </View>
      )}

      <BarcodeScannerModal
        visible={scannerVisible}
        onClose={() => setScannerVisible(false)}
        onScan={handleScan}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#000" },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    padding: 16,
    backgroundColor: "#1a1a1a",
  },
  title: { color: "#fff", fontSize: 20, fontWeight: "bold" },
  subtitle: { color: "#888", fontSize: 16, marginTop: 20 },
  centered: { flex: 1, justifyContent: "center", alignItems: "center", backgroundColor: "#000" },
  syncBadge: {
    color: "#FFD700",
    backgroundColor: "#333",
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 4,
    fontSize: 12,
  },
  cartSection: { flex: 1, padding: 16 },
  empty: { color: "#666", textAlign: "center", marginTop: 40, fontSize: 16 },
  cartItem: {
    flexDirection: "column",
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: "#333",
  },
  cartItemName: { color: "#fff", fontSize: 16 },
  cartItemRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    marginTop: 4,
  },
  cartItemPrice: { color: "#888", fontSize: 14, width: 60 },
  qtyButton: {
    backgroundColor: "#333",
    width: 28,
    height: 28,
    borderRadius: 14,
    alignItems: "center",
    justifyContent: "center",
  },
  qty: { color: "#fff", fontSize: 16, width: 20, textAlign: "center" },
  removeBtn: { color: "#FF3B30", fontSize: 16 },
  totals: {
    padding: 16,
    borderTopWidth: 1,
    borderTopColor: "#333",
    backgroundColor: "#1a1a1a",
  },
  totalRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    paddingVertical: 4,
  },
  totalLabel: { color: "#888", fontSize: 16 },
  totalValue: { color: "#fff", fontSize: 16, fontWeight: "bold" },
  actions: {
    flexDirection: "row",
    gap: 8,
    padding: 16,
    backgroundColor: "#111",
  },
  actionBtn: {
    flex: 2,
    backgroundColor: "#34C759",
    paddingVertical: 14,
    borderRadius: 8,
    alignItems: "center",
  },
  actionBtnDisabled: { backgroundColor: "#333" },
  actionBtnSecondary: {
    flex: 1,
    backgroundColor: "#222",
    paddingVertical: 14,
    borderRadius: 8,
    alignItems: "center",
    borderWidth: 1,
    borderColor: "#444",
  },
  actionBtnText: { color: "#000", fontWeight: "bold", fontSize: 16 },
  actionBtnTextSecondary: { color: "#fff", fontSize: 14 },
  error: { color: "#FF3B30", paddingHorizontal: 16, fontSize: 12 },
  resultBanner: {
    backgroundColor: "#333",
    padding: 12,
    alignItems: "center",
  },
  resultText: { color: "#FFD700", fontWeight: "bold", fontSize: 14 },
});
