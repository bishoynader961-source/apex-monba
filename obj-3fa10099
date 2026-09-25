import React, { useState, useEffect, useCallback } from "react";
import { View, Text, TouchableOpacity, Modal, StyleSheet, Alert, ActivityIndicator } from "react-native";
import { CameraView, Camera } from "expo-camera";
import { useNetInfo } from "@react-native-community/netinfo";

interface BarcodeScannerModalProps {
  visible: boolean;
  onClose: () => void;
  onScan: (barcode: string) => void;
}

export default function BarcodeScannerModal({ visible, onClose, onScan }: BarcodeScannerModalProps) {
  const [hasPermission, setHasPermission] = useState<boolean | null>(null);
  const [scanning, setScanning] = useState(true);

  useEffect(() => {
    const getPermission = async () => {
      const { status } = await Camera.requestCameraPermissionsAsync();
      setHasPermission(status === "granted");
    };
    if (visible) {
      getPermission();
      setScanning(true);
    }
  }, [visible]);

  const handleBarcodeScanned = useCallback(
    (event: { data: string; type: string }) => {
      if (!scanning) return;
      setScanning(false);
      onScan(event.data);
      onClose();
    },
    [scanning, onScan, onClose],
  );

  if (!visible) return null;

  if (hasPermission === null) {
    return (
      <Modal visible={visible} transparent={true} animationType="slide">
        <View style={styles.centered}>
          <ActivityIndicator size="large" color="#007AFF" />
          <Text style={styles.text}>Requesting camera permission...</Text>
        </View>
      </Modal>
    );
  }

  if (hasPermission === false) {
    return (
      <Modal visible={visible} transparent={true} animationType="slide">
        <View style={styles.centered}>
          <Text style={styles.text}>Camera permission denied</Text>
          <TouchableOpacity style={styles.btn} onPress={onClose}>
            <Text style={styles.btnText}>Close</Text>
          </TouchableOpacity>
        </View>
      </Modal>
    );
  }

  return (
    <Modal visible={visible} transparent={true} animationType="slide">
      <View style={styles.scannerContainer}>
        <CameraView
          style={StyleSheet.absoluteFill}
          onBarcodeScanned={scanning ? handleBarcodeScanned : undefined}
          barcodeScannerSettings={{
            barcodeTypes: ["upc_a", "upc_e", "ean13", "ean8", "code128", "code39", "itf14", "codabar"],
          }}
        />
        <View style={styles.overlay}>
          <Text style={styles.instruction}>Point camera at product barcode</Text>
          <TouchableOpacity style={styles.closeBtn} onPress={onClose}>
            <Text style={styles.closeBtnText}>✕</Text>
          </TouchableOpacity>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  scannerContainer: { flex: 1, backgroundColor: "#000" },
  overlay: {
    position: "absolute",
    bottom: 40,
    left: 0,
    right: 0,
    alignItems: "center",
  },
  instruction: {
    color: "#fff",
    fontSize: 16,
    backgroundColor: "rgba(0,0,0,0.7)",
    paddingHorizontal: 20,
    paddingVertical: 10,
    borderRadius: 8,
    marginBottom: 16,
  },
  closeBtn: {
    backgroundColor: "#FF3B30",
    width: 50,
    height: 50,
    borderRadius: 25,
    alignItems: "center",
    justifyContent: "center",
  },
  closeBtnText: { color: "#fff", fontSize: 24, fontWeight: "bold" },
  centered: {
    flex: 1,
    backgroundColor: "#000",
    justifyContent: "center",
    alignItems: "center",
    gap: 16,
  },
  text: { color: "#fff", fontSize: 16 },
  btn: {
    backgroundColor: "#007AFF",
    paddingHorizontal: 24,
    paddingVertical: 12,
    borderRadius: 8,
  },
  btnText: { color: "#fff", fontWeight: "bold" },
});
