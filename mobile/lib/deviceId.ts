import AsyncStorage from "@react-native-async-storage/async-storage";
import * as Device from "expo-device";
import { v4 as uuidv4 } from "uuid";

export const DEVICE_ID_KEY = "pp_device_id";

export function getDeviceName(): string {
  return `${Device.osName ?? "unknown"}_${Device.modelName ?? "dev"}`;
}

export async function getStoredDeviceId(): Promise<string> {
  const existing = await AsyncStorage.getItem(DEVICE_ID_KEY);
  if (existing) return existing;
  const id = uuidv4();
  await AsyncStorage.setItem(DEVICE_ID_KEY, id);
  return id;
}
