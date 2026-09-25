"use client";

import { useAuthStore, useCan } from "@/stores/authStore";

interface RouteGuardProps {
  permission: string;
  children: React.ReactNode;
}

export function RouteGuard({ permission, children }: RouteGuardProps) {
  const canAccess = useCan(permission);
  const user = useAuthStore((s) => s.user);

  const isAdmin = user?.role_id === 1 || user?.permissions?.includes("*");

  if (isAdmin || canAccess) {
    return <>{children}</>;
  }

  return (
    <div className="p-8 text-center bg-[#1a1a2e] border border-gray-800 rounded-lg">
      <h2 className="text-xl font-semibold text-gray-800 dark:text-gray-100 mb-2">
        Unauthorized Access
      </h2>
      <p className="text-gray-600 dark:text-gray-400">
        You need the <code className="px-1 bg-gray-800 rounded">{permission}</code> permission to access this page.
      </p>
    </div>
  );
}