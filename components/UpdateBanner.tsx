"use client";

import { X, Download } from "lucide-react";

interface UpdateBannerProps {
  currentVersion: string;
  latestVersion: string;
  downloadUrl: string | null;
  releaseNotes: string | null;
  onDismiss: () => void;
}

export function UpdateBanner({ currentVersion, latestVersion, downloadUrl, releaseNotes, onDismiss }: UpdateBannerProps) {
  return (
    <div className="bg-blue-600/15 border border-blue-600/30 rounded-lg p-4 mb-4">
      <div className="flex items-start justify-between">
        <div className="flex items-start gap-3">
          <div className="w-8 h-8 rounded-full bg-blue-600/20 flex items-center justify-center flex-shrink-0 mt-0.5">
            <Download className="w-4 h-4 text-blue-400" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-blue-400">Update Available</h3>
            <p className="text-xs text-gray-600 dark:text-gray-400 mt-1">
              Version {latestVersion} is available (current: {currentVersion})
            </p>
            {releaseNotes && (
              <p className="text-xs text-gray-500 mt-1 max-w-md">{releaseNotes}</p>
            )}
            {downloadUrl && (
              <a
                href={downloadUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 mt-2 text-xs text-blue-400 hover:text-blue-300"
              >
                <Download className="w-3 h-3" /> Download Update
              </a>
            )}
          </div>
        </div>
        <button onClick={onDismiss} className="text-gray-500 hover:text-gray-300 flex-shrink-0">
          <X className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
