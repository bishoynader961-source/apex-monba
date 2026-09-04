"use client";

import Link from "next/link";

import { useI18n } from "@/components/I18nProvider";

const LINKS = [
  { href: "/dashboard", labelKey: "nav.dashboard" },
  { href: "/pos", labelKey: "nav.pos" },
  { href: "/dashboard/inventory", labelKey: "nav.inventory" },
  { href: "/patients", labelKey: "nav.patients" },
  { href: "/prescribers", labelKey: "nav.prescribers" },
  { href: "/dashboard/wc-claims", labelKey: "nav.wcClaims" },
  { href: "/dashboard/analytics/demand", labelKey: "nav.analytics" },
  { href: "/dashboard/users", labelKey: "nav.users" },
  { href: "/dashboard/roles", labelKey: "nav.roles" },
  { href: "/dashboard/audit", labelKey: "nav.auditLog" },
  { href: "/dashboard/email", labelKey: "nav.email" },
  { href: "/dashboard/backup", labelKey: "nav.backup" },
  { href: "/dashboard/settings", labelKey: "nav.settings" },
];

export function DashboardNav({ active }: { active?: string }) {
  const { t } = useI18n();
  return (
    <nav className="flex flex-wrap gap-2 mb-4 border-b border-gray-700 pb-3">
      {LINKS.map((link) => (
        <Link
          key={link.href}
          href={link.href}
          className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
            active === link.href
              ? "bg-blue-600 text-white"
              : "text-gray-300 hover:text-white hover:bg-gray-800"
          }`}
        >
          {t(link.labelKey)}
        </Link>
      ))}
    </nav>
  );
}
