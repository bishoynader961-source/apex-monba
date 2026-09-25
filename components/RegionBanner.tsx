"use client";

import { useRegionStore } from "@/stores/regionStore";
import { useRouter } from "next/navigation";
import { MapPin, Settings, X } from "lucide-react";

export function RegionBanner() {
  const region = useRegionStore((s) => s.region);
  const bannerDismissed = useRegionStore((s) => s.bannerDismissed);
  const dismissBanner = useRegionStore((s) => s.dismissBanner);
  const router = useRouter();

  if (!region || bannerDismissed) return null;

  return (
    <div className="flex items-center justify-between px-4 py-2.5 rounded-lg border transition-colors"
      style={{
        background: "color-mix(in srgb, var(--primary) 10%, var(--bg-card))",
        borderColor: "color-mix(in srgb, var(--primary) 30%, transparent)",
      }}
    >
      <div className="flex items-center gap-2.5 min-w-0">
        <MapPin className="w-4 h-4 flex-shrink-0" style={{ color: "var(--primary)" }} />
        <span className="text-sm truncate" style={{ color: "var(--fg)" }}>
          Region auto-detected:{" "}
          <span className="font-semibold">{region.name}</span>{" "}
          <span className="opacity-60">
            ({region.currency_symbol} · {region.tax_label})
          </span>
        </span>
      </div>
      <div className="flex items-center gap-1.5 flex-shrink-0 ml-3">
        <button
          onClick={() => router.push("/dashboard/settings")}
          className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-md transition-colors"
          style={{
            color: "var(--primary)",
            background: "color-mix(in srgb, var(--primary) 10%, transparent)",
          }}
        >
          <Settings className="w-3 h-3" />
          Change Region
        </button>
        <button
          onClick={dismissBanner}
          className="p-1 rounded-md transition-colors"
          style={{ color: "var(--fg-muted)" }}
          title="Dismiss"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}
