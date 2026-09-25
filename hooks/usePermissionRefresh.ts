"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";
import { useAuthStore } from "@/stores/authStore";
import { getCurrentUser } from "@/lib/api/auth";

/**
 * Hook to automatically refresh user permissions on route change.
 * Calls GET /api/v1/auth/me when the pathname changes and updates the auth store
 * if permissions have changed. Handles user deactivation by logging out.
 */
export function usePermissionRefresh() {
  const pathname = usePathname();
  const { fetchCurrentUser, user } = useAuthStore();

  useEffect(() => {
    if (!user) return; // Don't refresh if not logged in

    const refreshPermissions = async () => {
      try {
        const freshUser = await getCurrentUser();
        if (freshUser === null) {
          // User deactivated or token invalid - log out
          useAuthStore.getState().logout();
          return;
        }
        void freshUser;

        // Check if permissions changed using the store's built-in method
        const changed = useAuthStore.getState().permissionsChanged();

        if (changed) {
          // Update the store with new permissions
          useAuthStore.getState().fetchCurrentUser();
        }
      } catch (err) {
        console.error("Permission refresh failed:", err);
      }
    };

    refreshPermissions();
  }, [pathname, user]);

  return null;
}

export function useAuthPermissions() {
  const user = useAuthStore((s) => s.user);
  const lastPermissions = useAuthStore((s) => s.lastPermissions);
  const permissionsChanged = useAuthStore((s) => {
    const current = s.user?.permissions ?? [];
    return current.length !== s.lastPermissions.length ||
      current.some((p) => !s.lastPermissions.includes(p)) ||
      s.lastPermissions.some((p) => !current.includes(p));
  });

  return {
    user,
    lastPermissions,
    permissionsChanged,
    refresh: () => useAuthStore.getState().fetchCurrentUser(),
  };
}

/**
 * Wrapper component to use the permission refresh hook in JSX
 */
export function PermissionRefreshProvider({ children }: { children: React.ReactNode }) {
  usePermissionRefresh();
  return children;
}