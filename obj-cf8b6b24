"use client";

import { useVersionCheck } from "@/hooks/useVersionCheck";
import { UpdateBanner } from "@/components/UpdateBanner";

export function VersionProvider({ children }: { children: React.ReactNode }) {
  const { info, dismiss } = useVersionCheck();

  return (
    <>
      {info?.update_available && info.latest_version && (
        <div className="max-w-7xl mx-auto px-4 pt-4">
          <UpdateBanner
            currentVersion={info.current_version}
            latestVersion={info.latest_version}
            downloadUrl={info.download_url}
            releaseNotes={info.release_notes}
            onDismiss={dismiss}
          />
        </div>
      )}
      {children}
    </>
  );
}
