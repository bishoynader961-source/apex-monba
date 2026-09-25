"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useI18n } from "@/components/I18nProvider";
import { DashboardLayout } from "@/components/DashboardLayout";
import { useAuthStore, useCan } from "@/stores/authStore";
import { getEmailHealth, sendDailySalesReport } from "@/lib/api/email";
import { RouteGuard } from "@/components/RouteGuard";
import type { EmailHealthResponse } from "@/lib/api/email";

export default function EmailPage() {
  const { t } = useI18n();
  const router = useRouter();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const canRead = useCan("email.read");

  const [health, setHealth] = useState<EmailHealthResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [toEmail, setToEmail] = useState("");
  const [reportDate, setReportDate] = useState("");
  const [sending, setSending] = useState(false);
  const [sendResult, setSendResult] = useState<string | null>(null);

  useEffect(() => {
    if (!isAuthenticated()) router.replace("/login");
  }, [isAuthenticated, router]);

  useEffect(() => {
    if (!canRead) return;
    loadHealth();
  }, [canRead]);

  async function loadHealth() {
    setLoading(true);
    setError(null);
    try {
      const data = await getEmailHealth();
      setHealth(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load email health");
    } finally {
      setLoading(false);
    }
  }

  async function handleSend() {
    if (!toEmail) return;
    setSending(true);
    setError(null);
    setSendResult(null);
    try {
      const result = await sendDailySalesReport({
        to_email: toEmail,
        report_date: reportDate || undefined,
      });
      setSendResult(result.message);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to send report");
    } finally {
      setSending(false);
    }
  }

  return (
    <DashboardLayout>
      <RouteGuard permission="email.read">
      <div className="p-4 md:p-6">
        <h1 className="text-2xl font-bold text-gray-800 dark:text-gray-100 mb-4">{t("email.title")}</h1>

        {error && (
          <div className="bg-red-900/30 text-red-400 border border-red-800 rounded-md px-4 py-3 mb-3">
            {error}
          </div>
        )}

        {sendResult && (
          <div className="bg-green-900/30 text-green-400 border border-green-800 rounded-md px-4 py-3 mb-3">
            {sendResult}
          </div>
        )}

        {loading ? (
          <p className="text-gray-600 dark:text-gray-400">{t("email.loadingSmtp")}</p>
        ) : health && (
          <div className="bg-[#111] rounded-lg border border-gray-800 p-5 mb-5">
            <h2 className="text-base font-semibold text-gray-800 dark:text-gray-100 mb-3">{t("email.smtpConfiguration")}</h2>
            <div className="flex items-center gap-3 mb-4">
              <span className={`inline-block w-2.5 h-2.5 rounded-full ${
                health.smtp_configured ? "bg-green-500" : "bg-red-500"
              }`} />
              <span className="text-sm text-gray-700 dark:text-gray-300">
                {health.smtp_configured ? t("email.smtpConfigured") : t("email.smtpNotConfigured")}
              </span>
            </div>
            {health.smtp_configured && (
              <dl className="text-sm grid gap-y-1 gap-x-4" style={{ gridTemplateColumns: "140px 1fr" }}>
                <dt className="text-gray-600 dark:text-gray-400">{t("email.host")}</dt>
                <dd className="text-gray-800 dark:text-gray-200 font-mono">{health.smtp_host}</dd>
                <dt className="text-gray-600 dark:text-gray-400">{t("email.port")}</dt>
                <dd className="text-gray-800 dark:text-gray-200">{health.smtp_port}</dd>
                <dt className="text-gray-600 dark:text-gray-400">{t("email.tls")}</dt>
                <dd className="text-gray-800 dark:text-gray-200">{health.smtp_tls ? t("users.yes") : t("users.no")}</dd>
                <dt className="text-gray-600 dark:text-gray-400">{t("email.from")}</dt>
                <dd className="text-gray-800 dark:text-gray-200">{health.from_email || "—"}</dd>
              </dl>
            )}
          </div>
        )}

        <div className="bg-[#111] rounded-lg border border-gray-800 p-5">
          <h2 className="text-base font-semibold text-gray-800 dark:text-gray-100 mb-3">{t("email.sendDailySales")}</h2>
          <div className="grid grid-cols-2 gap-3 max-w-[500px]">
            <div>
              <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1" htmlFor="page-field-1">{t("email.fieldToEmail")}</label>
              <input id="page-field-1"
                type="email"
                value={toEmail}
                onChange={(e) => setToEmail(e.target.value)}
                placeholder="manager@pharmacy.com"
                className="w-full px-3 py-2 border border-gray-700 bg-[#0d0d20] text-gray-800 dark:text-gray-200 rounded-md text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1" htmlFor="page-field-2">{t("email.fieldReportDate")}</label>
              <input id="page-field-2"
                type="date"
                value={reportDate}
                onChange={(e) => setReportDate(e.target.value)}
                className="w-full px-3 py-2 border border-gray-700 bg-[#0d0d20] text-gray-800 dark:text-gray-200 rounded-md text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>
          </div>
          <button
            onClick={handleSend}
            disabled={sending || !toEmail || !health?.smtp_configured}
            className={`mt-4 px-5 py-2 rounded-md text-sm font-medium cursor-pointer ${
              sending || !toEmail || !health?.smtp_configured
                ? "bg-gray-600 text-gray-400 cursor-default"
                : "bg-blue-600 text-white hover:bg-blue-700"
            }`}
          >
            {sending ? t("common.saving") : t("email.sendReport")}
          </button>
        </div>
      </div>
    </RouteGuard>
    </DashboardLayout>
  );
}
