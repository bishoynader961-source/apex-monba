"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useI18n } from "@/components/I18nProvider";
import { DashboardLayout } from "@/components/DashboardLayout";
import { useAuthStore, useCan } from "@/stores/authStore";
import * as rolesApi from "@/lib/api/roles";
import type { RoleRead, PermissionRead } from "@/lib/api/roles";

export default function RolesPage() {
  const { t } = useI18n();
  const router = useRouter();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const canRead = useCan("users.read");
  const canWrite = useCan("users.write");

  const [roles, setRoles] = useState<RoleRead[]>([]);
  const [allPermissions, setAllPermissions] = useState<PermissionRead[]>([]);
  const [selectedRole, setSelectedRole] = useState<RoleRead | null>(null);
  const [rolePermissions, setRolePermissions] = useState<number[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);

  useEffect(() => {
    if (!isAuthenticated()) router.replace("/login");
  }, [isAuthenticated, router]);

  useEffect(() => {
    if (!canRead) return;
    loadData();
  }, [canRead]);

  async function loadData() {
    setLoading(true);
    setError(null);
    try {
      const [r, p] = await Promise.all([rolesApi.listRoles(), rolesApi.listAllPermissions()]);
      setRoles(r);
      setAllPermissions(p);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load roles");
    } finally {
      setLoading(false);
    }
  }

  async function selectRole(role: RoleRead) {
    setSelectedRole(role);
    try {
      const perms = await rolesApi.getRolePermissions(role.id);
      setRolePermissions(perms);
    } catch {
      setRolePermissions([]);
    }
  }

  async function togglePermission(permId: number) {
    if (!selectedRole || !canWrite) return;
    const next = rolePermissions.includes(permId)
      ? rolePermissions.filter((id) => id !== permId)
      : [...rolePermissions, permId];
    setRolePermissions(next);
    try {
      await rolesApi.setRolePermissions(selectedRole.id, next);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to update permissions");
    }
  }

  async function handleDeleteRole(role: RoleRead) {
    if (role.is_system) { setError("Cannot delete system roles"); return; }
    if (!confirm(`Delete role "${role.name}"?`)) return;
    try {
      await rolesApi.updateRole(role.id, { name: `deleted_${role.id}` });
      await loadData();
      if (selectedRole?.id === role.id) setSelectedRole(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to delete role");
    }
  }

  return (
    <DashboardLayout>
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-2xl font-bold text-gray-100">{t("roles.title")}</h1>
        {canWrite && (
          <button onClick={() => setCreateOpen(true)} className="px-4 py-2 bg-green-600 text-white rounded-md text-sm font-medium hover:bg-green-700">
            {t("roles.newRole")}
          </button>
        )}
      </div>

      {error && (
        <div className="bg-red-900/30 text-red-400 border border-red-600/40 px-4 py-3 rounded-lg mb-4">
          {error}
        </div>
      )}

      {loading ? (
        <p className="text-gray-400">{t("roles.loading")}</p>
      ) : (
        <div className="flex gap-6">
          {/* Roles list */}
          <div className="flex-1 bg-[#111] rounded-lg border border-gray-800 overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-800">
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-400 uppercase tracking-wider">{t("roles.colRole")}</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-400 uppercase tracking-wider">{t("roles.colDescription")}</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-400 uppercase tracking-wider">{t("roles.colType")}</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody>
                {roles.map((r) => (
                  <tr
                    key={r.id}
                    onClick={() => void selectRole(r)}
                    className={`cursor-pointer border-b border-gray-800/50 ${selectedRole?.id === r.id ? "bg-blue-900/20" : "hover:bg-white/5"}`}
                  >
                    <td className="px-4 py-3 text-sm font-medium text-gray-200">{r.name}</td>
                    <td className="px-4 py-3 text-sm text-gray-400">{r.description || "—"}</td>
                    <td className="px-4 py-3">
                      <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${r.is_system ? "bg-blue-900/30 text-blue-400" : "bg-gray-800 text-gray-400"}`}>
                        {r.is_system ? t("roles.typeSystem") : t("roles.typeCustom")}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      {canWrite && !r.is_system && (
                        <div className="flex gap-1">
                          <button onClick={(e) => { e.stopPropagation(); setEditOpen(true); setSelectedRole(r); }} className="text-xs text-blue-400 hover:text-blue-300">
                            {t("roles.edit")}
                          </button>
                          <button onClick={(e) => { e.stopPropagation(); void handleDeleteRole(r); }} className="text-xs text-red-400 hover:text-red-300">
                            {t("roles.delete")}
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Permission matrix */}
          {selectedRole && (
            <div className="flex-[2] bg-[#111] rounded-lg border border-gray-800 p-5 self-start">
              <h2 className="text-base font-semibold text-gray-100 mb-1">{t("roles.permissionsTitle")}: {selectedRole.name}</h2>
              <p className="text-xs text-gray-400 mb-3">
                {selectedRole.is_system ? t("roles.systemRoleHint") : t("roles.toggleHint")}
              </p>
              <div className="grid grid-cols-2 gap-1">
                {allPermissions.map((p) => {
                  const granted = rolePermissions.includes(p.id);
                  return (
                    <button
                      key={p.id}
                      onClick={() => void togglePermission(p.id)}
                      disabled={!canWrite || !!selectedRole.is_system}
                      className={`flex items-center gap-2 px-2.5 py-1.5 text-xs rounded border text-left ${
                        granted
                          ? "border-green-600 bg-green-900/20 text-green-400"
                          : "border-gray-700 bg-[#0d0d20] text-gray-400"
                      } ${canWrite && !selectedRole.is_system ? "cursor-pointer hover:bg-white/5" : "cursor-default"}`}
                    >
                      <span className={`w-2 h-2 rounded-full flex-shrink-0 ${granted ? "bg-green-500" : "bg-gray-600"}`} />
                      <span>{p.feature_key}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {createOpen && (
        <CreateRoleModal
          onClose={() => setCreateOpen(false)}
          onSuccess={() => { void loadData(); setCreateOpen(false); }}
        />
      )}

      {editOpen && selectedRole && (
        <EditRoleModal
          role={selectedRole}
          onClose={() => setEditOpen(false)}
          onSuccess={() => { void loadData(); setEditOpen(false); }}
        />
      )}
    </DashboardLayout>
  );
}

// ── Create Role Modal ────────────────────────────────────────────────────────

function CreateRoleModal({ onClose, onSuccess }: { onClose: () => void; onSuccess: () => void }) {
  const { t } = useI18n();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    if (!name.trim()) { setError("Name is required"); return; }
    setSaving(true);
    setError(null);
    try {
      await rolesApi.createRole({ name: name.trim(), description: description.trim() || undefined });
      onSuccess();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Create failed");
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
      <div className="w-full max-w-[400px] bg-[#111] rounded-lg border border-gray-800 p-6 shadow-xl">
        <h2 className="text-lg font-semibold text-gray-100 mb-4">{t("roles.modalNew")}</h2>
        {error && <p className="text-sm text-red-400 mb-3">{error}</p>}
        <div className="flex flex-col gap-3">
          <div>
            <label className="block text-sm font-medium text-gray-400 mb-1">{t("roles.fieldName")}</label>
            <input value={name} onChange={(e) => setName(e.target.value)} autoFocus className="w-full px-3 py-2 bg-[#1a1a2e] border border-gray-700 rounded-md text-sm text-gray-200 focus:outline-none focus:border-blue-500" />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-400 mb-1">{t("roles.fieldDescription")}</label>
            <input value={description} onChange={(e) => setDescription(e.target.value)} className="w-full px-3 py-2 bg-[#1a1a2e] border border-gray-700 rounded-md text-sm text-gray-200 focus:outline-none focus:border-blue-500" />
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-5">
          <button onClick={onClose} disabled={saving} className="px-4 py-2 border border-gray-600 rounded-md text-sm text-gray-400 hover:bg-gray-800 disabled:opacity-50">{t("common.cancel")}</button>
          <button onClick={() => void handleSubmit()} disabled={saving || !name.trim()} className={`px-4 py-2 rounded-md text-sm font-medium text-white ${saving || !name.trim() ? "bg-gray-600 cursor-default" : "bg-green-600 hover:bg-green-700"}`}>
            {saving ? "Creating..." : t("roles.create")}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Edit Role Modal ──────────────────────────────────────────────────────────

function EditRoleModal({ role, onClose, onSuccess }: { role: RoleRead; onClose: () => void; onSuccess: () => void }) {
  const { t } = useI18n();
  const [name, setName] = useState(role.name);
  const [description, setDescription] = useState(role.description ?? "");
  const [saving, setSaving] = useState(false);

  const handleSubmit = async () => {
    setSaving(true);
    try {
      await rolesApi.updateRole(role.id, { name: name.trim(), description: description.trim() || undefined });
      onSuccess();
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
      <div className="w-full max-w-[400px] bg-[#111] rounded-lg border border-gray-800 p-6 shadow-xl">
        <h2 className="text-lg font-semibold text-gray-100 mb-4">{t("roles.modalEdit")}</h2>
        <div className="flex flex-col gap-3">
          <div>
            <label className="block text-sm font-medium text-gray-400 mb-1">{t("common.name")}</label>
            <input value={name} onChange={(e) => setName(e.target.value)} autoFocus className="w-full px-3 py-2 bg-[#1a1a2e] border border-gray-700 rounded-md text-sm text-gray-200 focus:outline-none focus:border-blue-500" />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-400 mb-1">{t("roles.fieldDescription")}</label>
            <input value={description} onChange={(e) => setDescription(e.target.value)} className="w-full px-3 py-2 bg-[#1a1a2e] border border-gray-700 rounded-md text-sm text-gray-200 focus:outline-none focus:border-blue-500" />
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-5">
          <button onClick={onClose} disabled={saving} className="px-4 py-2 border border-gray-600 rounded-md text-sm text-gray-400 hover:bg-gray-800 disabled:opacity-50">{t("common.cancel")}</button>
          <button onClick={() => void handleSubmit()} disabled={saving} className="px-4 py-2 rounded-md text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-50">
            {saving ? t("common.saving") : t("common.save")}
          </button>
        </div>
      </div>
    </div>
  );
}
