import React, { useState } from "react";
import { View, Text, TouchableOpacity, TextInput, StyleSheet, Alert } from "react-native";
import { usePosStore } from "../stores/posStore";
import { formatMoney, parseMoney } from "../lib/decimalCurrency";

export default function ShiftsScreen() {
  const { currentShiftId, openShift, closeShift, error } = usePosStore();
  const [openingFloat, setOpeningFloat] = useState("");
  const [countedCash, setCountedCash] = useState("");

  const handleOpenShift = async () => {
    if (!openingFloat) {
      Alert.alert("Error", "Enter an opening float amount");
      return;
    }
    try {
      await openShift(openingFloat);
    } catch {
      Alert.alert("Error", error ?? "Failed to open shift");
    }
  };

  const handleCloseShift = async () => {
    if (!countedCash) {
      Alert.alert("Error", "Enter the counted cash amount");
      return;
    }
    try {
      await closeShift(countedCash);
      Alert.alert("Shift Closed", "Good luck out there!");
    } catch {
      Alert.alert("Error", error ?? "Failed to close shift");
    }
  };

  if (currentShiftId) {
    return (
      <View style={styles.container}>
        <Text style={styles.title}>Shift #{currentShiftId} Active</Text>
        <View style={styles.card}>
          <Text style={styles.label}>Counted Cash</Text>
          <TextInput
            style={styles.input}
            placeholder="0.00"
            placeholderTextColor="#666"
            keyboardType="numeric"
            value={countedCash}
            onChangeText={setCountedCash}
          />
          <TouchableOpacity style={styles.btn} onPress={handleCloseShift}>
            <Text style={styles.btnText}>Close Shift</Text>
          </TouchableOpacity>
        </View>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Open Shift</Text>
      <View style={styles.card}>
        <Text style={styles.label}>Opening Float</Text>
        <TextInput
          style={styles.input}
          placeholder="0.00"
          placeholderTextColor="#666"
          keyboardType="numeric"
          value={openingFloat}
          onChangeText={setOpeningFloat}
        />
        <TouchableOpacity style={styles.btn} onPress={handleOpenShift}>
          <Text style={styles.btnText}>Open Shift</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#000", padding: 16 },
  title: { color: "#fff", fontSize: 24, fontWeight: "bold", marginBottom: 16 },
  card: {
    backgroundColor: "#1a1a1a",
    padding: 20,
    borderRadius: 12,
    gap: 12,
  },
  label: { color: "#aaa", fontSize: 14, marginBottom: 4 },
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
  btnText: { color: "#fff", fontWeight: "bold", fontSize: 16 },
});
