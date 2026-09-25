"use client";

import { useEffect, useState } from "react";

interface VersionInfo {
  current_version: string;
  latest_version: string | null;
  update_available: boolean;
  download_url: string | null;
  release_notes: string | null;
}

export function useVersionCheck() {
  const [info, setInfo] = useState<VersionInfo | null>(null);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    const token = localStorage.getItem("access_token");
    if (!token) return;

    fetch("/api/v1/version", {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((data: VersionInfo | null) => {
        if (data?.update_available) {
          const dismissedVersion = localStorage.getItem("dismissed_update_version");
          if (dismissedVersion !== data.latest_version) {
            setInfo(data);
          }
        }
      })
      .catch(() => {});
  }, []);

  const dismiss = () => {
    if (info?.latest_version) {
      localStorage.setItem("dismissed_update_version", info.latest_version);
    }
    setDismissed(true);
    setInfo(null);
  };

  return { info, dismissed, dismiss };
}
