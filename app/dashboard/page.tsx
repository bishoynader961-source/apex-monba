"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { DashboardLayout } from "@/components/DashboardLayout";
import { useAuthStore } from "@/stores/authStore";
import { useI18n } from "@/components/I18nProvider";

export default function DashboardPage() {
  const { t } = useI18n();
  const router = useRouter();
  const user = useAuthStore((s) => s.user);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const logout = useAuthStore((s) => s.logout);

  const MODULES = [
    {
      href: "/pos",
      label: t("dashboard.posLabel"),
      desc: t("dashboard.posDesc"),
      color: "bg-emerald-600 hover:bg-emerald-700",
    },
    {
      href: "/dashboard/inventory",
      label: t("dashboard.inventoryLabel"),
      desc: t("dashboard.inventoryDesc"),
      color: "bg-blue-600 hover:bg-blue-700",
    },
    {
      href: "/patients",
      label: t("dashboard.patientsLabel"),
      desc: t("dashboard.patientsDesc"),
      color: "bg-purple-600 hover:bg-purple-700",
    },
    {
      href: "/dashboard/analytics/demand",
      label: t("dashboard.analyticsLabel"),
      desc: t("dashboard.analyticsDesc"),
      color: "bg-amber-600 hover:bg-amber-700",
    },
  ];

  useEffect(() => {
    if (!isAuthenticated()) {
      router.replace("/login");
    }
  }, [isAuthenticated, router]);

  if (!isAuthenticated()) return null;

  return (
    <DashboardLayout>
      <h1 className="text-2xl font-bold text-gray-100 mb-2">
        {t("dashboard.title")}
      </h1>
      {user && (
        <p className="text-sm text-gray-400 mb-6">
          {t("dashboard.signedInAs")} <span className="text-gray-200">{user.username}</span>
        </p>
      )}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {MODULES.map((mod) => (
          <Link
            key={mod.href}
            href={mod.href}
            className={`rounded-lg p-5 text-left text-white transition-colors ${mod.color}`}
          >
            <h2 className="text-lg font-semibold mb-1">{mod.label}</h2>
            <p className="text-sm text-white/80">{mod.desc}</p>
          </Link>
        ))}
      </div>
    </DashboardLayout>
  );
}
