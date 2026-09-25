"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const SEGMENT_LABELS: Record<string, string> = {
  dashboard: "Dashboard",
  pos: "Point of Sale",
  inventory: "Inventory",
  patients: "Patients",
  prescribers: "Prescribers",
  analytics: "Analytics",
  "expiry-alerts": "Expiry Alerts",
  "wc-claims": "WC Claims",
  vendors: "Vendors",
  "receiving-log": "Receiving Log",
  "purchase-orders": "Purchase Orders",
  "drug-interactions": "Drug Interactions",
  drugs: "Drugs",
  "quick-sig": "Quick Sig",
  "sig-codes": "SIG Codes",
  templates: "Templates",
  "bulk-import": "Bulk Import",
  "bulk-label-print": "Bulk Label Print",
  "label-engine": "Label Engine",
  "invoice-parse": "Invoice Parse",
  "gift-cards": "Gift Cards",
  users: "Users",
  roles: "Roles",
  backup: "Backup",
  settings: "Settings",
  audit: "Audit Log",
  email: "Email",
  demand: "Demand Forecast",
  license: "License",
  rx: "Prescriptions",
  "print-label": "Print Label",
  portal: "Portal",
};

export function Breadcrumbs() {
  const pathname = usePathname();
  if (!pathname || pathname === "/dashboard") return null;

  const segments = pathname.split("/").filter(Boolean);
  const crumbs = segments.map((seg, i) => ({
    label: SEGMENT_LABELS[seg] ?? seg.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
    href: "/" + segments.slice(0, i + 1).join("/"),
    isLast: i === segments.length - 1,
  }));

  return (
    <nav className="flex items-center gap-1 text-sm text-textMuted" aria-label="Breadcrumb">
      <Link href="/dashboard" className="hover:text-primary transition-colors">
        Home
      </Link>
      {crumbs.map((crumb) => (
        <span key={crumb.href} className="flex items-center gap-1">
          <span className="text-gray-700 dark:text-gray-300">/</span>
          {crumb.isLast ? (
            <span className="font-medium text-textMain">{crumb.label}</span>
          ) : (
            <Link href={crumb.href} className="hover:text-primary transition-colors">
              {crumb.label}
            </Link>
          )}
        </span>
      ))}
    </nav>
  );
}
