import React, { useState, useCallback } from "react";
import { View, Text, TouchableOpacity, StyleSheet, Alert, TextInput, Modal } from "react-native";
import { useInventoryStore } from "../stores/inventoryStore";
import { formatMoney, parseMoney } from "../lib/decimalCurrency";
import BarcodeScannerModal from "../components/BarcodeScanner";
import type { ProductRead, InventoryAdjustmentCreate } from "../types/contracts";
import * as inventoryApi from "../lib/api/inventory";

export default function InventoryScannerScreen() {
  const [scannerVisible, setScannerVisible] = useState(false);
  const [scannedProduct, setScannedProduct] = useState<ProductRead | null>(null);
  const [loadingProduct, setLoadingProduct] = useState(false);
  const [adjusting, setAdjusting] = useState(false);
  const [adjustQuantity, setAdjustQuantity] = useState("");
  const [adjustReason, setAdjustReason] = useState("");
  const [showAdjustModal, setShowAdjustModal] = useState(false);

  const handleScan = useCallback(async (barcode: string) => {
    setLoadingProduct(true);
    try {
      const product = await inventoryApi.getProductByBarcode(barcode);
      setScannedProduct(product);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Product not found";
      Alert.alert("Scan Result", msg);
      setScannedProduct(null);
    } finally {
      setLoadingProduct(false);
    }
  }, []);

  const handleAdjust = useCallback(async () => {
    if (!scannedProduct) return;
    const qty = parseInt(adjustQuantity, 10);
    if (isNaN(qty)) {
      Alert.alert("Error", "Enter a valid quantity");
      return;
    }
    if (!adjustReason.trim()) {
      Alert.alert("Error", "Enter a reason for adjustment");
      return;
    }

    setAdjusting(true);
    try {
      const payload: InventoryAdjustmentCreate = {
        product_name: scannedProduct.name,
        change: qty,
        reason: adjustReason.trim(),
        client_timestamp: new Date().toISOString(),
      };
      await inventoryApi.adjustInventory(payload);
      Alert.alert("Success", `Stock adjusted by ${qty > 0 ? "+" : ""}${qty}`);
      setShowAdjustModal(false);
      setAdjustQuantity("");
      setAdjustReason("");
      // Refresh product info
      const refreshed = await inventoryApi.getProductByBarcode(scannedProduct.internal_unique_barcode);
      setScannedProduct(refreshed);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed to adjust inventory";
      Alert.alert("Error", msg);
    } finally {
      setAdjusting(false);
    }
  }, [scannedProduct, adjustQuantity, adjustReason]);

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>Inventory Scanner</Text>
      </View>

      <TouchableOpacity style={styles.scanBtn} onPress={() => setScannerVisible(true)} disabled={loadingProduct}>
        {loadingProduct ? (
          <Text style={styles.scanBtnText}>Scanning...</Text>
        ) : (
          <Text style={styles.scanBtnText}>📷 Scan Barcode</Text>
        )}
      </TouchableOpacity>

      {scannedProduct && (
        <View style={styles.productCard}>
          <Text style={styles.productName}>{scannedProduct.name}</Text>
          <Text style={styles.productBarcode}>Barcode: {scannedProduct.internal_unique_barcode}</Text>
          <Text style={styles.productPrice}>Price: {formatMoney(parseMoney(scannedProduct.price))}</Text>
          <Text style={styles.productExpiry}>
            Expiry: {scannedProduct.expiry_date || "N/A"}
          </Text>
          <Text
            style={[
              styles.productStock,
              scannedProduct.reorder_threshold && scannedProduct.reorder_threshold > 0
                ? { color: "#FF3B30" }
                : {},
            ]}
          >
            Reorder Threshold: {scannedProduct.reorder_threshold ?? "N/A"}
          </Text>

          <TouchableOpacity
            style={[styles.adjustBtn, adjustReason || adjustQuantity ? {} : styles.adjustBtnDisabled]}
            onPress={() => setShowAdjustModal(true)}
            disabled={adjusting}
          >
            <Text style={styles.adjustBtnText}>✏️ Adjust Stock</Text>
          </TouchableOpacity>
        </View>
      )}

      {!scannedProduct && !loadingProduct && (
        <Text style={styles.hint}>Scan a product barcode to view details and adjust stock</Text>
      )}

      <BarcodeScannerModal
        visible={scannerVisible}
        onClose={() => setScannerVisible(false)}
        onScan={handleScan}
      />

      <Modal visible={showAdjustModal} animationType="slide" transparent>
        <View style={styles.modalOverlay}>
          <View style={styles.modalContent}>
            <Text style={styles.modalTitle}>Adjust Stock</Text>
            <Text style={styles.modalProduct}>{scannedProduct?.name}</Text>

            <TextInput
              style={styles.modalInput}
              placeholder="Quantity change (e.g., +5 or -3)"
              value={adjustQuantity}
              onChangeText={setAdjustQuantity}
              keyboardType="numeric"
            />

            <TextInput
              style={styles.modalInput}
              placeholder="Reason (e.g., 'damage', 'recount', 'return')"
              value={adjustReason}
              onChangeText={setAdjustReason}
              multiline
              numberOfLines={3}
            />

            <View style={styles.modalButtons}>
              <TouchableOpacity style={styles.modalBtnCancel} onPress={() => setShowAdjustModal(false)}>
                <Text style={styles.modalBtnText}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.modalBtnConfirm, adjusting && styles.modalBtnDisabled]}
                onPress={handleAdjust}
                disabled={adjusting}
              >
                <Text style={styles.modalBtnText}>{adjusting ? "Saving..." : "Save"}</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#000", padding: 16 },
  header: { marginBottom: 24 },
  title: { color: "#fff", fontSize: 28, fontWeight: "bold" },
  scanBtn: {
    backgroundColor: "#007AFF",
    paddingVertical: 18,
    borderRadius: 12,
    alignItems: "center",
    marginBottom: 24,
  },
  scanBtnText: { color: "#fff", fontSize: 18, fontWeight: "bold" },
  productCard: {
    backgroundColor: "#1a1a1a",
    borderRadius: 12,
    padding: 20,
    marginBottom: 16,
    borderWidth: 1,
    borderColor: "#333",
  },
  productName: { color: "#fff", fontSize: 20, fontWeight: "bold", marginBottom: 8 },
  productBarcode: { color: "#888", fontSize: 14, fontFamily: "monospace", marginBottom: 4 },
  productPrice: { color: "#34C759", fontSize: 18, fontWeight: "bold", marginBottom: 4 },
  productExpiry: { color: "#FF9500", fontSize: 14, marginBottom: 4 },
  productStock: { color: "#aaa", fontSize: 14, marginBottom: 16 },
  adjustBtn: { backgroundColor: "#FF9500", paddingVertical: 12, borderRadius: 8, alignItems: "center" },
  adjustBtnDisabled: { opacity: 0.5 },
  adjustBtnText: { color: "#000", fontSize: 16, fontWeight: "bold" },
  hint: { color: "#555", fontSize: 14, textAlign: "center", marginTop: 32 },
  modalOverlay: { flex: 1, backgroundColor: "rgba(0,0,0,0.7)", justifyContent: "center", padding: 16 },
  modalContent: {
    backgroundColor: "#1a1a1a",
    borderRadius: 12,
    padding: 20,
    borderWidth: 1,
    borderColor: "#333",
  },
  modalTitle: { color: "#fff", fontSize: 20, fontWeight: "bold", marginBottom: 4 },
  modalProduct: { color: "#888", fontSize: 14, marginBottom: 16 },
  modalInput: {
    backgroundColor: "#222",
    color: "#fff",
    padding: 12,
    borderRadius: 8,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: "#333",
  },
  modalButtons: { flexDirection: "row", gap: 12, marginTop: 8 },
  modalBtnCancel: { flex: 1, backgroundColor: "#333", paddingVertical: 12, borderRadius: 8, alignItems: "center" },
  modalBtnConfirm: { flex: 1, backgroundColor: "#007AFF", paddingVertical: 12, borderRadius: 8, alignItems: "center" },
  modalBtnDisabled: { opacity: 0.6 },
  modalBtnText: { color: "#fff", fontWeight: "bold", fontSize: 16 },
});