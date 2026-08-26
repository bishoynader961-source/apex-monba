"use client";

import { ReactNode } from "react";

export function LoadingSplash() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-gray-50 dark:bg-gray-900">
      <div className="text-center">
        <div className="mb-4 h-8 w-8 animate-spin rounded-full border-2 border-blue-600 border-t-transparent mx-auto"></div>
        <p className="text-sm text-gray-500 dark:text-gray-400">Loading…</p>
      </div>
    </main>
  );
}
