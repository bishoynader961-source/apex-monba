"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import { useI18n } from "@/components/I18nProvider";
import { useAuthStore } from "@/stores/authStore";

const NAV_SECTIONS = [
  {
    label: "Operations",
    items: [
      { href: "/pos", labelKey: "nav.pos", icon: "🛒" },
      { href: "/dashboard/inventory", labelKey: "nav.inventory", icon: "📦" },
      { href: "/patients", labelKey: "nav.patients", icon: "👤" },
      { href: "/prescribers", labelKey: "nav.prescribers", icon: "📋" },
      { href: "/dashboard/wc-claims", labelKey: "nav.wcClaims", icon: "📄" },
      { href: "/dashboard/vendors", labelKey: "nav.vendors", icon: "🏢" },
    ],
  },
  {
    label: "Insights",
    items: [
      { href: "/dashboard/analytics", labelKey: "nav.salesAnalytics", icon: "📈" },
      { href: "/dashboard/analytics/demand", labelKey: "nav.analytics", icon: "📊" },
      { href: "/dashboard/audit", labelKey: "nav.auditLog", icon: "🔍" },
      { href: "/dashboard/email", labelKey: "nav.email", icon: "📧" },
    ],
  },
  {
    label: "Administration",
    items: [
      { href: "/dashboard/users", labelKey: "nav.users", icon: "👥" },
      { href: "/dashboard/roles", labelKey: "nav.roles", icon: "🔐" },
      { href: "/dashboard/backup", labelKey: "nav.backup", icon: "💾" },
      { href: "/dashboard/settings", labelKey: "nav.settings", icon: "⚙️" },
    ],
  },
];

export function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { t } = useI18n();
  const pathname = usePathname();
  const router = useRouter();
  const user = useAuthStore((s) => s.user);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const logout = useAuthStore((s) => s.logout);

  useEffect(() => {
    if (!isAuthenticated()) router.replace("/login");
  }, [isAuthenticated, router]);

  if (!isAuthenticated()) return null;

  return (
    <div className="flex h-screen overflow-hidden bg-[#0a0a1a]">
      {/* Sidebar */}
      <aside className="w-56 flex-shrink-0 bg-[#0d0d20] border-r border-gray-800 flex flex-col">
        {/* Logo */}
        <div className="px-4 py-4 border-b border-gray-800">
          <Link href="/dashboard" className="text-lg font-bold text-white tracking-tight">
            💊 Pharmacy Suite
          </Link>
        </div>

        {/* Navigation */}
        <nav className="flex-1 overflow-y-auto py-2">
          {NAV_SECTIONS.map((section) => (
            <div key={section.label} className="mb-2">
              <div className="px-4 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-gray-500">
                {section.label}
              </div>
              {section.items.map((item) => {
                const isActive = pathname === item.href || pathname?.startsWith(item.href + "/");
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`flex items-center gap-2.5 px-4 py-2 text-sm transition-colors ${
                      isActive
                        ? "bg-blue-600/20 text-blue-400 border-r-2 border-blue-400"
                        : "text-gray-400 hover:text-gray-200 hover:bg-white/5"
                    }`}
                  >
                    <span className="text-base">{item.icon}</span>
                    <span>{t(item.labelKey)}</span>
                  </Link>
                );
              })}
            </div>
          ))}
        </nav>

        {/* User footer */}
        <div className="px-4 py-3 border-t border-gray-800 bg-[#0a0a18]">
          <div className="flex items-center justify-between">
            <div className="min-w-0">
              <div className="text-sm font-medium text-gray-200 truncate">
                {user?.username ?? "User"}
              </div>
              <div className="text-xs text-gray-500 truncate">
                {user?.role ?? "Admin"}
              </div>
            </div>
            <button
              onClick={() => logout()}
              className="ml-2 px-2.5 py-1 text-xs text-gray-400 hover:text-red-400 hover:bg-red-400/10 rounded transition-colors"
              title="Logout"
            >
              ⏻
            </button>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-y-auto bg-[#0a0a1a]">
        <div className="p-6">{children}</div>
      </main>
    </div>
  );
}
