import { useCallback } from "react";
import { usePosStore } from "../../stores/posStore";

export function useShift() {
  const { currentShiftId, openShift, closeShift, error } = usePosStore();

  const isOpen = currentShiftId !== null;

  const open = useCallback(
    async (openingFloat: string) => {
      await openShift(openingFloat);
      return currentShiftId;
    },
    [openShift, currentShiftId],
  );

  const close = useCallback(
    async (countedCash: string) => {
      await closeShift(countedCash);
    },
    [closeShift],
  );

  return {
    shiftId: currentShiftId,
    isOpen,
    open,
    close,
    error,
  };
}
