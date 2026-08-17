/**
 * Inventory data hook (M3-FL).
 *
 * Thin React wrapper over `stores/inventoryStore`. Keeps the exact public shape
 * the dashboard inventory page already consumes (medicines, stockLevels,
 * suppliers, canWrite, isLoading, error, search, applyFilters, refetch,
 * receiveBatch, adjustBatch, updateMedicine, deleteMedicine) so no page changes
 * are required — only the backing state moved into the global store.
 */
import { useEffect, useRef } from "react";

import { useAuthStore } from "@/stores/authStore";
import { useInventoryStore } from "@/stores/inventoryStore";
import type { InventoryFilters } from "@/types/contracts";

export function useInventory(initialFilters: InventoryFilters = {}) {
  const medicines = useInventoryStore((s) => s.medicines);
  const stockLevels = useInventoryStore((s) => s.stockLevels);
  const suppliers = useInventoryStore((s) => s.suppliers);
  const isLoading = useInventoryStore((s) => s.isLoading);
  const error = useInventoryStore((s) => s.error);

  const loadSuppliers = useInventoryStore((s) => s.loadSuppliers);
  const applyFilters = useInventoryStore((s) => s.applyFilters);
  const search = useInventoryStore((s) => s.search);
  const refetch = useInventoryStore((s) => s.refetch);
  const loadStockLevels = useInventoryStore((s) => s.loadStockLevels);
  const receiveBatch = useInventoryStore((s) => s.receiveBatch);
  const adjustBatch = useInventoryStore((s) => s.adjustBatch);
  const updateMedicine = useInventoryStore((s) => s.updateMedicine);
  const deleteMedicine = useInventoryStore((s) => s.deleteMedicine);

  const hasPermission = useAuthStore((s) => s.hasPermission);
  const canWrite = hasPermission("inventory.write");

  const initialRef = useRef(initialFilters);

  // Initial load: suppliers + first filtered page + stock-level alerts.
  useEffect(() => {
    void loadSuppliers();
    void applyFilters(initialRef.current);
    void loadStockLevels();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return {
    medicines,
    stockLevels,
    suppliers,
    canWrite,
    isLoading,
    error,
    search,
    applyFilters,
    refetch,
    receiveBatch,
    adjustBatch,
    updateMedicine,
    deleteMedicine,
  };
}
