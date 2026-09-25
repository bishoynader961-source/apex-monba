"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useI18n } from "@/components/I18nProvider";
import { DashboardLayout } from "@/components/DashboardLayout";
import { useAuthStore, useCan } from "@/stores/authStore";
import { verifyAuditChain, exportAuditLogs } from "@/lib/api/audit";
import { RouteGuard } from "@/components/RouteGuard";
import type { AuditVerifyResult } from "@/types/contracts";

export default function AuditPage() {
  const { t } = useI18n();
  const router = useRouter();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const canRead = useCan("audit.read");

  const [verifyResult, setVerifyResult] = useState<AuditVerifyResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    if (!isAuthenticated()) router.replace("/login");
  }, [isAuthenticated, router]);

  useEffect(() => {
    if (!canRead) return;
    verify();
  }, [canRead]);

  async function verify() {
    setLoading(true);
    setError(null);
    try {
      const result = await verifyAuditChain();
      setVerifyResult(result);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to verify audit chain");
    } finally {
      setLoading(false);
    }
  }

  async function handleExport(fmt: "json" | "csv") {
    setExporting(true);
    try {
      const blob = await exportAuditLogs(fmt);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `audit-logs.${fmt}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to export audit logs");
    } finally {
      setExporting(false);
    }
  }

  return (
    <DashboardLayout>
      <RouteGuard permission="audit.read">
      <div className="p-4 md:p-6">
        <h1 className="text-2xl font-bold text-gray-800 dark:text-gray-100 mb-4">{t("audit.title")}</h1>

        {error && (
          <div className="bg-red-900/30 text-red-400 border border-red-800 rounded-md px-4 py-3 mb-3">
            {error}
          </div>
        )}

        <div className="flex gap-4 mb-5">
          <button
            onClick={() => verify()}
            disabled={loading}
            className="px-4 py-2 rounded-md border border-gray-700 bg-[#1a1a2e] text-gray-800 dark:text-gray-200 text-sm hover:bg-[#222244] disabled:opacity-50 disabled:cursor-default cursor-pointer"
          >
            {loading ? t("audit.verifying") : t("audit.reVerifyChain")}
          </button>
          <button
            onClick={() => handleExport("json")}
            disabled={exporting}
            className="px-4 py-2 rounded-md border border-gray-700 bg-[#1a1a2e] text-gray-800 dark:text-gray-200 text-sm hover:bg-[#222244] disabled:opacity-50 disabled:cursor-default cursor-pointer"
          >
            {t("audit.exportJson")}
          </button>
          <button
            onClick={() => handleExport("csv")}
            disabled={exporting}
            className="px-4 py-2 rounded-md border border-gray-700 bg-[#1a1a2e] text-gray-800 dark:text-gray-200 text-sm hover:bg-[#222244] disabled:opacity-50 disabled:cursor-default cursor-pointer"
          >
            {t("audit.exportCsv")}
          </button>
        </div>

        {verifyResult && (
          <div className="bg-[#111] rounded-lg border border-gray-800 p-5">
            <h2 className="text-base font-semibold text-gray-800 dark:text-gray-100 mb-3">{t("audit.chainResult")}</h2>
            <div className="flex items-center gap-3">
              <span
                className={`inline-block w-3 h-3 rounded-full ${
                  verifyResult.valid ? "bg-green-500" : "bg-red-500"
                }`}
              />
              <span className={`text-base font-medium ${verifyResult.valid ? "text-green-400" : "text-red-400"}`}>
                {verifyResult.valid ? t("audit.chainIntact") : t("audit.chainCompromised")}
              </span>
            </div>
            {!verifyResult.valid && verifyResult.broken_at && (
              <p className="mt-2 text-sm text-red-400">
                {t("audit.firstBreak")} {verifyResult.broken_at}
              </p>
            )}
          </div>
        )}
      </div>
    </RouteGuard>
    </DashboardLayout>
  );
}
