"use client";

import { useAuthStore } from "@/stores/authStore";

export function hasPermission(user: { role_id?: number; permissions?: string[] } | null | undefined, requiredPermission: string): boolean {
  if (!user) return false;
  if (user.role_id === 1) return true;
  if (user.permissions?.includes("*")) return true;
  return user.permissions?.includes(requiredPermission) ?? false;
}

export function useHasPermission(permission: string): boolean {
  return useAuthStore((s) => hasPermission(s.user, permission));
}

export function useIsAdmin(): boolean {
  return useAuthStore((s) => (s.user?.role_id === 1 || s.user?.permissions?.includes("*")) ?? false);
}