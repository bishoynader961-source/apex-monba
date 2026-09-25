import { useEffect, useRef } from "react";
import NetInfo from "@react-native-community/netinfo";
import { usePosStore } from "../../stores/posStore";

let isFlushing = false;

export function useSync() {
  const flushQueue = usePosStore((s) => s.flushQueue);
  const offlineCount = usePosStore((s) => s.offlineCount);
  const prevOnline = useRef(true);

  useEffect(() => {
    const unsubscribe = NetInfo.addEventListener(async (state) => {
      const online = state.isConnected ?? false;

      if (online && !prevOnline.current && offlineCount > 0 && !isFlushing) {
        isFlushing = true;
        try {
          await flushQueue();
        } catch (e) {
          console.error("useSync: flush failed", e);
        } finally {
          isFlushing = false;
        }
      }

      prevOnline.current = online;
    });

    return () => unsubscribe();
  }, [flushQueue, offlineCount]);
}
