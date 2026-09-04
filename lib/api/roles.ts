// Typed Roles API service (RBAC management).
import { api } from "@/lib/api";

export interface RoleRead {
  id: number;
  name: string;
  description?: string | null;
  is_system: number;
}

export interface PermissionRead {
  id: number;
  feature_key: string;
  description?: string | null;
}

const BASE = "/api/v1/roles";

export async function listRoles(): Promise<RoleRead[]> {
  const { data } = await api.get<RoleRead[]>(BASE);
  return data;
}

export async function getRole(id: number): Promise<RoleRead> {
  const { data } = await api.get<RoleRead>(`${BASE}/${id}`);
  return data;
}

export async function createRole(payload: { name: string; description?: string }): Promise<RoleRead> {
  const { data } = await api.post<RoleRead>(BASE, payload);
  return data;
}

export async function updateRole(id: number, payload: { name?: string; description?: string }): Promise<RoleRead> {
  const { data } = await api.put<RoleRead>(`${BASE}/${id}`, payload);
  return data;
}

export async function getRolePermissions(roleId: number): Promise<number[]> {
  const { data } = await api.get<number[]>(`${BASE}/${roleId}/permissions`);
  return data;
}

export async function setRolePermissions(roleId: number, permissionIds: number[]): Promise<{ permission_ids: number[] }> {
  const { data } = await api.put<{ permission_ids: number[] }>(`${BASE}/${roleId}/permissions`, { permission_ids: permissionIds });
  return data;
}

export async function listAllPermissions(): Promise<PermissionRead[]> {
  const { data } = await api.get<PermissionRead[]>(`${BASE}/permissions/all`);
  return data;
}
