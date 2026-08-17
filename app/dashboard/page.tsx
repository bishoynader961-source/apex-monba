"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useAuthStore } from "@/stores/authStore";

export default function DashboardPage() {
  const router = useRouter();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const logout = useAuthStore((s) => s.logout);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.replace("/login");
    }
  }, [isAuthenticated, router]);

  if (!isAuthenticated()) {
    return null;
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-gray-50 dark:bg-gray-900">
      <div className="w-full max-w-md space-y-6 rounded-lg bg-white dark:bg-gray-800 p-8 shadow-lg">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            Dashboard
          </h1>
          <button
            onClick={() => logout()}
            className="text-sm font-medium text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white"
          >
            Logout
          </button>
        </div>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          You are authenticated. Welcome to the Pharmacy Suite dashboard.
        </p>
      </div>
    </main>
  );
}
