import { useState, useCallback } from "react";
import { Alert } from "react-native";
import { useCameraPermissions } from "expo-camera";

export function useBarcodeScanner() {
  const [hasPermission, setHasPermission] = useState<boolean>(false);
  const [scanned, setScanned] = useState(false);
  const [permission, requestPermission] = useCameraPermissions();

  const requestCameraPermission = useCallback(async () => {
    if (permission?.granted) {
      setHasPermission(true);
      return true;
    }
    const result = await requestPermission();
    setHasPermission(result.granted);
    if (!result.granted) {
      Alert.alert("Permission Required", "Camera access is needed for barcode scanning");
    }
    return result.granted;
  }, [permission, requestPermission]);

  const onScanComplete = useCallback(
    (value: string) => {
      setScanned(true);
      return value;
    },
    [],
  );

  const resetScan = useCallback(() => {
    setScanned(false);
  }, []);

  return {
    hasPermission,
    scanned,
    requestCameraPermission,
    onScanComplete,
    resetScan,
  };
}
