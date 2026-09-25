"use client";

import { useEffect } from "react";
import { useRegionStore } from "@/stores/regionStore";

export function RegionProvider({ children }: { children: React.ReactNode }) {
  const detect = useRegionStore((s) => s.detect);
  const detected = useRegionStore((s) => s.detected);

  useEffect(() => {
    if (!detected) detect();
  }, [detected, detect]);

  return <>{children}</>;
}
