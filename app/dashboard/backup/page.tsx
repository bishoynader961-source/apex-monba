"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useI18n } from "@/components/I18nProvider";
import { DashboardLayout } from "@/components/DashboardLayout";
import { useAuthStore, useCan } from "@/stores/authStore";
import { createBackup } from "@/lib/api/admin";
import type { BackupResult } from "@/types/contracts";

export default function BackupPage() {
  const { t } = useI18n();
  const router = useRouter();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const canWrite = useCan("backup.create");

  const [backing, setBacking] = useState(false);
  const [result, setResult] = useState<BackupResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isAuthenticated()) router.replace("/login");
  }, [isAuthenticated, router]);

  async function handleBackup() {
    setBacking(true);
    setError(null);
    setResult(null);
    try {
      const res = await createBackup();
      setResult(res);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Backup failed");
    } finally {
      setBacking(false);
    }
  }

  return (
    <DashboardLayout>
      <div className="p-4 md:p-6">
        <h1 className="text-2xl font-bold text-gray-100 mb-4">{t("backup.title")}</h1>

        {error && (
          <div className="bg-red-900/30 text-red-400 border border-red-800 rounded-md px-4 py-3 mb-3">
            {error}
          </div>
        )}

        {result && (
          <div className="bg-green-900/30 text-green-400 border border-green-800 rounded-md px-4 py-3 mb-3">
            {t("backup.success")}
          </div>
        )}

        <div className="bg-[#111] rounded-lg border border-gray-800 p-5">
          <p className="text-sm text-gray-400 mb-4">
            {t("backup.description")}
          </p>

          <button
            onClick={handleBackup}
            disabled={backing || !canWrite}
            className={`px-6 py-2.5 rounded-md text-sm font-medium cursor-pointer ${
              backing || !canWrite
                ? "bg-gray-600 text-gray-400 cursor-default"
                : "bg-red-600 text-white hover:bg-red-700"
            }`}
          >
            {backing ? t("backup.creating") : t("backup.createBackup")}
          </button>

          {!canWrite && (
            <p className="mt-2 text-xs text-gray-500">{t("backup.noPermission")}</p>
          )}

          {result && (
            <div className="mt-5 p-4 bg-[#0d0d20] rounded-md text-sm">
              <dl className="grid gap-y-1 gap-x-4" style={{ gridTemplateColumns: "140px 1fr" }}>
                <dt className="text-gray-400">{t("backup.colPath")}</dt>
                <dd className="text-gray-200 font-mono text-xs">{result.path}</dd>
                <dt className="text-gray-400">{t("backup.colCompressed")}</dt>
                <dd className="text-gray-200">{result.compressed ? t("users.yes") : t("users.no")}</dd>
                <dt className="text-gray-400">{t("backup.colSize")}</dt>
                <dd className="text-gray-200">{(result.size_bytes / 1024).toFixed(1)} KB</dd>
              </dl>
            </div>
          )}
        </div>
      </div>
    </DashboardLayout>
  );
}
