"use client";

import Link from "next/link";

import { useI18n } from "@/components/I18nProvider";

const LINKS = [
  { href: "/dashboard", labelKey: "nav.dashboard" },
  { href: "/pos", labelKey: "nav.pos" },
  { href: "/dashboard/inventory", labelKey: "nav.inventory" },
  { href: "/dashboard/templates", labelKey: "nav.templates" },
  { href: "/dashboard/bulk-import", labelKey: "nav.bulkImport" },
  { href: "/dashboard/bulk-label-print", labelKey: "nav.bulkLabelPrint" },
  { href: "/dashboard/gift-cards", labelKey: "nav.giftCards" },
  { href: "/patients", labelKey: "nav.patients" },
  { href: "/prescribers", labelKey: "nav.prescribers" },
  { href: "/dashboard/wc-claims", labelKey: "nav.wcClaims" },
  { href: "/dashboard/analytics/demand", labelKey: "nav.analytics" },
  { href: "/dashboard/receiving-log", labelKey: "nav.receivingLog" },
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
    <nav className="mb-4 flex flex-wrap gap-2 border-b border-border pb-3">
      {LINKS.map((link) => (
        <Link
          key={link.href}
          href={link.href}
          className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
            active === link.href
              ? "bg-primary text-white"
              : "text-gray-600 hover:bg-gray-100 hover:text-gray-900"
          }`}
        >
          {t(link.labelKey)}
        </Link>
      ))}
    </nav>
  );
}
