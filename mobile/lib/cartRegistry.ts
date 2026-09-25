import AsyncStorage from "@react-native-async-storage/async-storage";

const CART_KEY = "cart_registry";

export interface CartRegistry {
  tab_id: string;
  lines: unknown[];
  saved_at: string;
  discount_type: string | null;
  discount_value: string | null;
  tax_exempt: boolean;
  price_overrides: Record<string, string>;
  payments: Array<{ method: string; amount: string }> | null;
}

export async function saveCart(registry: CartRegistry): Promise<void> {
  await AsyncStorage.setItem(CART_KEY, JSON.stringify(registry));
}

export async function getCart(): Promise<CartRegistry | null> {
  const raw = await AsyncStorage.getItem(CART_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as CartRegistry;
  } catch {
    return null;
  }
}

export async function clearCart(): Promise<void> {
  await AsyncStorage.removeItem(CART_KEY);
}

export function isCartAgeValid(savedAt: string, maxAgeHours = 4): boolean {
  const saved = new Date(savedAt).getTime();
  if (isNaN(saved)) return false;
  return Date.now() - saved < maxAgeHours * 3600 * 1000;
}
