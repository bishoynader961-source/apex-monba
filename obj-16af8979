import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo } from "react";

import { useI18n } from "@/components/I18nProvider";
import { BackButton } from "@/components/BackButton";
import { useAuthStore } from "@/stores/authStore";
import { OfflineSyncBanner } from "@/components/OfflineSyncBanner";
import { NetworkStatusBadge } from "@/components/NetworkStatusBadge";
import { CommandPalette } from "@/components/CommandPalette";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { RegionBanner } from "@/components/RegionBanner";
import { Breadcrumbs } from "@/components/navigation/Breadcrumbs";
import { Tooltip } from "@/components/ui/Tooltip";
import { Toaster } from "@/components/Toaster";
import { TOOLTIPS } from "@/lib/constants/tooltips";

const NAV_SECTIONS = [
  {
    label: "Operations",
    labelKey: "nav.section.operations",
    items: [
      { href: "/pos", labelKey: "nav.pos", icon: "🛒", permission: "pos.checkout" },
      { href: "/dashboard/inventory", labelKey: "nav.inventory", icon: "📦", permission: "inventory.read" },
      { href: "/dashboard/expiry-alerts", labelKey: "nav.expiryAlerts", icon: "⏰", permission: "inventory.read" },
      { href: "/patients", labelKey: "nav.patients", icon: "👤", permission: "patients.read" },
      { href: "/prescribers", labelKey: "nav.prescribers", icon: "📋", permission: "patients.read" },
      { href: "/dashboard/wc-claims", labelKey: "nav.wcClaims", icon: "📄", permission: "wc.read" },
      { href: "/dashboard/vendors", labelKey: "nav.vendors", icon: "🏢", permission: "inventory.read" },
      { href: "/dashboard/receiving-log", labelKey: "nav.receivingLog", icon: "📥", permission: "inventory.read" },
      { href: "/dashboard/purchase-orders", labelKey: "nav.purchaseOrders", icon: "🧾", permission: "inventory.read" },
      { href: "/dashboard/receipt-history", labelKey: "nav.receiptHistory", icon: "🧾", permission: "pos.checkout" },
    ],
  },
  {
    label: "Clinical",
    labelKey: "nav.section.clinical",
    items: [
      { href: "/dashboard/drug-interactions", labelKey: "nav.drugInteractions", icon: "⚕️", permission: "drugInteractions.read" },
      { href: "/dashboard/drugs", labelKey: "nav.drugs", icon: "💊", permission: "drugs.read" },
      { href: "/dashboard/quick-sig", labelKey: "nav.quickSig", icon: "✏️", permission: "quickSig.read" },
      { href: "/dashboard/sig-codes", labelKey: "nav.sigCodes", icon: "📑", permission: "sigCodes.read" },
    ],
  },
  {
    label: "Insights",
    labelKey: "nav.section.insights",
    items: [
      { href: "/dashboard/analytics", labelKey: "nav.salesAnalytics", icon: "📈", permission: "analytics.read" },
      { href: "/dashboard/analytics/demand", labelKey: "nav.analytics", icon: "📊", permission: "analytics.read" },
      { href: "/dashboard/audit", labelKey: "nav.auditLog", icon: "🔍", permission: "audit.read" },
      { href: "/dashboard/email", labelKey: "nav.email", icon: "📧", permission: "email.read" },
    ],
  },
  {
    label: "Tools",
    labelKey: "nav.section.tools",
    items: [
      { href: "/dashboard/templates", labelKey: "nav.templates", icon: "🎨", permission: "templates.read" },
      { href: "/dashboard/bulk-import", labelKey: "nav.bulkImport", icon: "📥", permission: "bulkImport.read" },
      { href: "/dashboard/bulk-label-print", labelKey: "nav.bulkLabelPrint", icon: "🏷️", permission: "bulkLabelPrint.read" },
      { href: "/dashboard/label-engine", labelKey: "nav.labelEngine", icon: "🔧", permission: "labelEngine.read" },
      { href: "/dashboard/invoice-parse", labelKey: "nav.invoiceParse", icon: "📄", permission: "invoiceParse.read" },
      { href: "/dashboard/gift-cards", labelKey: "nav.giftCards", icon: "🎁", permission: "giftCards.read" },
    ],
  },
  {
    label: "Administration",
    labelKey: "nav.section.administration",
    items: [
      { href: "/dashboard/users", labelKey: "nav.users", icon: "👥", permission: "users.read" },
      { href: "/dashboard/roles", labelKey: "nav.roles", icon: "🔐", permission: "users.read" },
      { href: "/dashboard/backup", labelKey: "nav.backup", icon: "💾", permission: "backup.read" },
      { href: "/dashboard/settings", labelKey: "nav.settings", icon: "⚙️", permission: "settings.read" },
      { href: "/dashboard/support", labelKey: "nav.support", icon: "💬" },
    ],
  },
];

export function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { t } = useI18n();
  const pathname = usePathname();
  const router = useRouter();
  const user = useAuthStore((s) => s.user);
  const token = useAuthStore((s) => s.token);
  const logout = useAuthStore((s) => s.logout);

  // Redirect to login when user becomes null AND token is null (true logout).
  // Do NOT redirect when token exists but user is null — that's a cold-start
  // refresh in progress. Place this at the top so it fires before any render.
  useEffect(() => {
    if (!user && !token) {
      router.replace("/login");
    }
  }, [user, token, router]);

  // Filter navigation sections based on user permissions
  const filteredSections = useMemo(() => {
    const perms = user?.permissions ?? [];
    const isAdmin = user?.role_id === 1 || perms.includes("*");
    
    // Admin sees EVERYTHING — no filtering, no conditions, just return all tabs
    if (isAdmin) return NAV_SECTIONS;
    
    // Non-admin: filter by permission
    return NAV_SECTIONS
      .map(section => ({
        ...section,
        items: section.items.filter(item =>
          !item.permission || perms.includes(item.permission)
        )
      }))
      .filter(section => section.items.length > 0);
  }, [user?.role_id, user?.permissions]);

  // Cold-start: token exists but user not yet loaded (refresh in progress)
  if (token && !user) {
    return (
      <div className="flex h-screen items-center justify-center bg-background">
        <div className="animate-spin rounded-full h-10 w-10 border-3 border-emerald-500 border-t-transparent"></div>
      </div>
    );
  }

  // No token and no user — the useEffect above will redirect, but avoid
  // rendering null (blank white screen) during the microtask gap.
  if (!token) {
    return (
      <div className="flex h-screen items-center justify-center bg-background">
        <div className="animate-spin rounded-full h-10 w-10 border-3 border-emerald-500 border-t-transparent"></div>
      </div>
    );
  }

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      <Toaster />
      {/* Sidebar */}
      <aside className="flex w-56 flex-shrink-0 flex-col bg-sidebar text-gray-900 dark:text-white">
        {/* Logo */}
        <div className="border-b border-white/10 px-4 py-4">
          <Link href="/dashboard" className="flex items-center gap-2 text-lg font-bold tracking-tight text-gray-900 dark:text-white">
            <span className="text-xl">💊</span>
            <span>Pharmacy Suite</span>
          </Link>
        </div>

        {/* Dashboard anchor — always first, above every section */}
        <Link
          href="/dashboard"
          className={`mx-2 mt-2 flex items-center gap-2.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
            pathname === "/dashboard"
              ? "bg-white/15 text-emerald-50"
              : "text-emerald-100 hover:bg-white/10 hover:text-emerald-50"
          }`}
        >
          <span className="text-base leading-none">🏠</span>
          <span>Dashboard</span>
        </Link>

        {/* Navigation */}
        <nav className="flex-1 overflow-y-auto py-2">
          {filteredSections.map((section) => (
            <div key={section.label} className="mb-1">
              <div className="px-4 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-emerald-100">
                {t(section.labelKey)}
              </div>
              {section.items.map((item) => {
                const isActive = pathname === item.href || pathname?.startsWith(item.href + "/");
                const tooltipText = TOOLTIPS[item.labelKey];
                const link = (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`mx-2 flex items-center gap-2.5 rounded-md px-3 py-1.5 text-sm transition-colors ${
                      isActive
                        ? "bg-white/15 text-emerald-50 font-medium"
                        : "text-emerald-100 hover:bg-white/10 hover:text-emerald-50"
                    }`}
                  >
                    <span className="text-base leading-none">{item.icon}</span>
                    <span>{t(item.labelKey)}</span>
                  </Link>
                );

                return tooltipText ? (
                  <Tooltip key={item.href} content={tooltipText} side="right">
                    {link}
                  </Tooltip>
                ) : (
                  link
                );
              })}
            </div>
          ))}
        </nav>

        {/* User footer */}
        <div className="border-t border-white/10 bg-black/20 px-4 py-3">
          <div className="mb-2 flex items-center gap-2">
            <LanguageSwitcher />
          </div>
          <div className="flex items-center justify-between">
            <div className="min-w-0">
              <div className="truncate text-sm font-medium text-emerald-50">
                {user?.username ?? "User"}
              </div>
              <div className="truncate text-xs text-emerald-200">
                {user?.role ?? "Admin"}
              </div>
            </div>
            <button
              onClick={() => logout()}
              className="ml-2 rounded px-2 py-1 text-xs text-emerald-200 transition-colors hover:text-emerald-50"
              title="Logout"
            >
              ⏻
            </button>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex flex-1 flex-col overflow-y-auto bg-background">
        <div className="sticky top-0 z-10 border-b border-border bg-surface px-6 py-3 shadow-sm">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-3">
              {pathname && pathname !== "/dashboard" && <BackButton />}
              <Breadcrumbs />
            </div>
            <div className="flex items-center gap-4">
              <NetworkStatusBadge />
              <OfflineSyncBanner />
            </div>
          </div>
        </div>
        <div className="flex-1 p-6">
          <RegionBanner />
          {children}
        </div>
      </main>
    </div>
  );
}