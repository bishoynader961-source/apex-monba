"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, useMemo } from "react";

import { useI18n } from "@/components/I18nProvider";
import { DashboardLayout } from "@/components/DashboardLayout";
import { RouteGuard } from "@/components/RouteGuard";
import { useAuthStore, useCan } from "@/stores/authStore";
import * as rolesApi from "@/lib/api/roles";
import type { RoleRead, PermissionRead } from "@/lib/api/roles";
import { listUsers } from "@/lib/api/users";
import { AuthConfirmModal } from "@/components/AuthConfirmModal";
import { useToast } from "@/hooks/useToast";
import { DataTable } from "@/components/DataTable";
import type { Column } from "@/components/DataTable";

const MODULES: Record<string, string> = {
  inventory: "Inventory",
  pos: "POS",
  users: "Users",
  settings: "Settings",
  patients: "Patients",
  insurance: "Insurance",
  members: "Members",
  dictionaries: "Dictionaries",
  dispense: "Dispense",
  analytics: "Analytics",
  backup: "Backup",
  coupons: "Coupons",
  rx: "Rx Queue",
  region: "Region",
  compounds: "Compounds",
  prior_auth: "Prior Auth",
  epcs: "EPCS",
};

function getModuleFromPermission(key: string): string {
  const prefix = key.split(".")[0];
  return MODULES[prefix] ?? prefix;
}

export default function RolesPage() {
  const { t } = useI18n();
  const router = useRouter();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const canRead = useCan("users.read");
  const canWrite = useCan("users.write");
  const canManage = useCan("users.manage");
  const user = useAuthStore((s) => s.user);

  const [roles, setRoles] = useState<RoleRead[]>([]);
  const [allPermissions, setAllPermissions] = useState<PermissionRead[]>([]);
  const [userCounts, setUserCounts] = useState<Record<number, number>>({});
  const [selectedRole, setSelectedRole] = useState<RoleRead | null>(null);
  const [rolePermissions, setRolePermissions] = useState<number[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [addPermOpen, setAddPermOpen] = useState(false);
  const [lockPassOpen, setLockPassOpen] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmAction, setConfirmAction] = useState<"togglePermission" | "deleteRole" | null>(null);
  const [confirmPermId, setConfirmPermId] = useState<number | null>(null);
  const [confirmRole, setConfirmRole] = useState<RoleRead | null>(null);
  const { toast } = useToast();

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
      try {
        const users = await listUsers();
        const counts: Record<number, number> = {};
        for (const u of users) counts[u.role_id] = (counts[u.role_id] ?? 0) + 1;
        setUserCounts(counts);
      } catch {
        // user counts are informational only
      }
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
    setConfirmAction("togglePermission");
    setConfirmPermId(permId);
    setConfirmOpen(true);
  }

  async function handleConfirmAction() {
    if (!selectedRole || !confirmAction) return;
    try {
      if (confirmAction === "togglePermission" && confirmPermId !== null) {
        const next = rolePermissions.includes(confirmPermId)
          ? rolePermissions.filter((id) => id !== confirmPermId)
          : [...rolePermissions, confirmPermId];
        setRolePermissions(next);
        await rolesApi.setRolePermissions(selectedRole.id, next);
        toast({ title: "Success", message: "Permission updated" });
      } else if (confirmAction === "deleteRole" && confirmRole) {
        await rolesApi.updateRole(confirmRole.id, { name: `deleted_${confirmRole.id}` });
        await loadData();
        if (selectedRole?.id === confirmRole.id) setSelectedRole(null);
        toast({ title: "Success", message: "Role deleted" });
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to update");
    } finally {
      setConfirmOpen(false);
      setConfirmAction(null);
      setConfirmPermId(null);
      setConfirmRole(null);
    }
  }

  async function handleDeleteRole(role: RoleRead) {
    if (role.is_system) { setError("Cannot delete system roles"); return; }
    setConfirmAction("deleteRole");
    setConfirmRole(role);
    setConfirmOpen(true);
  }

  const permissionsByModule = useMemo(() => {
    const grouped: Record<string, PermissionRead[]> = {};
    allPermissions.forEach((p) => {
      const moduleName = getModuleFromPermission(p.feature_key);
      if (!grouped[moduleName]) grouped[moduleName] = [];
      grouped[moduleName].push(p);
    });
    return grouped;
  }, [allPermissions]);

  const columns = useMemo<Column<RoleRead>[]>(() => [
    {
      key: "name",
      header: t("roles.colRole"),
      render: (row) => {
        const n = userCounts[row.id] ?? 0;
        return `${row.name} (${n} user${n === 1 ? "" : "s"})`;
      },
    },
    { key: "description", header: t("roles.colDescription"), render: (row) => row.description || "—" },
    {
      key: "type",
      header: t("roles.colType"),
      render: (row) => (
        <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${row.is_system ? "bg-blue-900/30 text-blue-400" : "bg-gray-800 text-gray-400"}`}>
          {row.is_system ? t("roles.typeSystem") : t("roles.typeCustom")}
        </span>
      ),
    },
    {
      key: "actions",
      header: "",
      render: (row) => {
        if (!canWrite || row.is_system) return null;
        return (
          <div className="flex gap-1">
            <button onClick={(e) => { e.stopPropagation(); setEditOpen(true); setSelectedRole(row); }} className="text-xs text-blue-400 hover:text-blue-300">
              {t("roles.edit")}
            </button>
            <button onClick={(e) => { e.stopPropagation(); void handleDeleteRole(row); }} className="text-xs text-red-400 hover:text-red-300">
              {t("roles.delete")}
            </button>
          </div>
        );
      },
    },
  ], [t, canWrite, userCounts]);

  const actions = useMemo<{ header: string; render: (row: RoleRead) => React.ReactNode }>(() => ({
    header: "",
    render: (row) => {
      if (!canWrite || row.is_system) return null;
      return (
        <div className="flex gap-1">
          <button onClick={(e) => { e.stopPropagation(); setEditOpen(true); setSelectedRole(row); }} className="text-xs text-blue-400 hover:text-blue-300">
            {t("roles.edit")}
          </button>
          <button onClick={(e) => { e.stopPropagation(); void handleDeleteRole(row); }} className="text-xs text-red-400 hover:text-red-300">
            {t("roles.delete")}
          </button>
        </div>
      );
    }
  }), [canWrite, t]);

  return (
    <DashboardLayout>
      <RouteGuard permission="users.read">
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-2xl font-bold text-gray-800 dark:text-gray-100">{t("roles.title")}</h1>
        {canManage && (
          <div className="flex gap-2">
            {user?.role_id === 1 && (
              <button onClick={() => setLockPassOpen(true)} className="px-4 py-2 bg-purple-600 text-white rounded-md text-sm font-medium hover:bg-purple-700">
                {t("roles.setLockPassword") ?? "Set Lock Password"}
              </button>
            )}
            <button onClick={() => setAddPermOpen(true)} className="px-4 py-2 bg-blue-600 text-white rounded-md text-sm font-medium hover:bg-blue-700">
              {t("roles.addPermission") ?? "Add Permission"}
            </button>
            <button onClick={() => setCreateOpen(true)} className="px-4 py-2 bg-green-600 text-white rounded-md text-sm font-medium hover:bg-green-700">
              {t("roles.newRole")}
            </button>
          </div>
        )}
      </div>

      {error && (
        <div className="bg-red-900/30 text-red-400 border border-red-600/40 px-4 py-3 rounded-lg mb-4">
          {error}
        </div>
      )}

      {loading ? (
        <p className="text-gray-600 dark:text-gray-400">{t("roles.loading")}</p>
      ) : (
        <div className="flex gap-6">
          {/* Roles list */}
          <div className="flex-1 bg-[#111] rounded-lg border border-gray-800 overflow-hidden">
            <DataTable
              columns={columns}
              data={roles}
              keyExtractor={(row) => row.id}
              loading={loading}
              emptyMessage={t("roles.noResults")}
              onRowClick={selectRole}
              selection={{
                selectedKeys: selectedRole ? new Set([selectedRole.id]) : new Set(),
                onSelectionChange: (keys) => {
                  if (keys.size > 0) {
                    const selected = roles.find((r) => r.id === Array.from(keys)[0]);
                    if (selected) selectRole(selected);
                  }
                },
              }}
              actions={actions}
            />
          </div>

          {/* Permission matrix */}
          {selectedRole && (
            <div className="flex-[2] bg-[#111] rounded-lg border border-gray-800 p-5 self-start">
              <h2 className="text-base font-semibold text-gray-800 dark:text-gray-100 mb-1">{t("roles.permissionsTitle")}: {selectedRole.name}</h2>
              <p className="text-xs text-gray-600 dark:text-gray-400 mb-3">
                {selectedRole.is_system ? t("roles.systemRoleHint") : t("roles.toggleHint")}
              </p>
              <div className="space-y-4 max-h-[60vh] overflow-y-auto">
                {Object.entries(permissionsByModule).map(([module, perms]) => (
                  <div key={module} className="space-y-2">
                    <h3 className="text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider mb-2">{module}</h3>
                    <div className="grid grid-cols-2 gap-1">
                      {perms.map((p) => {
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
                ))}
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

      {confirmOpen && (
        <AuthConfirmModal
          isOpen={confirmOpen}
          onClose={() => { setConfirmOpen(false); setConfirmAction(null); setConfirmPermId(null); setConfirmRole(null); }}
          onConfirm={handleConfirmAction}
          title={confirmAction === "togglePermission" ? t("roles.confirmPermTitle") : t("roles.confirmDeleteTitle")}
          message={confirmAction === "togglePermission" ? t("roles.confirmPermMessage", { perm: allPermissions.find(p => p.id === confirmPermId)?.feature_key ?? "" }) : t("roles.confirmDeleteMessage", { name: confirmRole?.name ?? "" })}
          actionName={confirmAction === "togglePermission" ? t("roles.updatePermission") : t("roles.delete")}
        />
      )}

      {addPermOpen && (
        <AddPermissionModal
          onClose={() => setAddPermOpen(false)}
          onSuccess={() => { void loadData(); setAddPermOpen(false); }}
          modules={MODULES}
        />
      )}

      {lockPassOpen && (
        <LockPasswordModal
          onClose={() => setLockPassOpen(false)}
          onSuccess={() => { void loadData(); setLockPassOpen(false); }}
        />
      )}
      </RouteGuard>
    </DashboardLayout>
  );
}

// ── Add Permission Modal ──────────────────────────────────────────────────────
function AddPermissionModal({
  onClose,
  onSuccess,
  modules,
}: {
  onClose: () => void;
  onSuccess: () => void;
  modules: Record<string, string>;
}) {
  const { t } = useI18n();
  const [description, setDescription] = useState("");
  const [module, setModule] = useState("");
  const [action, setAction] = useState("");
  const [otherAction, setOtherAction] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const ACTIONS = ["view", "create", "edit", "delete", "export", "print", "manage", "other"];

  // Compute feature key based on dropdowns
  const currentAction = action === "other" ? otherAction : action;
  const featureKey = module && currentAction ? `${module}.${currentAction}` : "";

  const handleSubmit = async () => {
    if (!featureKey.trim() || !description.trim() || !module || !action) {
      setError(t("roles.addPermAllFieldsRequired") ?? "All fields are required");
      return;
    }
    if (action === "other" && !otherAction.trim()) {
      setError(t("roles.addPermActionRequired") ?? "Action name is required when 'Other' is selected");
      return;
    }
    // Validate format: module.action
    if (!/^[a-z]+\.[a-z]+$/.test(featureKey.trim())) {
      setError(t("roles.addPermFormatError") ?? "Feature key must be in format: module.action (lowercase, e.g., reports.view)");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await rolesApi.createPermission({ feature_key: featureKey.trim(), description: description.trim() });
      onSuccess();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Create failed");
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
      <div className="w-full max-w-[480px] bg-[#111] rounded-lg border border-gray-800 p-6 shadow-xl">
        <h2 className="text-lg font-semibold text-gray-100 mb-4">{t("roles.addPermission") ?? "Add Permission"}</h2>
        {error && <p className="text-sm text-red-400 mb-3">{error}</p>}
        <div className="flex flex-col gap-4">
          <div className="flex gap-3">
            <div className="flex-1">
              <label className="block text-sm font-medium text-gray-600 dark:text-gray-400 mb-1" htmlFor="page-field-1">{t("roles.fieldModule") ?? "Module"}</label>
              <select id="page-field-1"
                value={module}
                onChange={(e) => setModule(e.target.value)}
                className="w-full px-3 py-2 bg-[#1a1a2e] border border-gray-700 rounded-md text-sm text-gray-200 focus:outline-none focus:border-blue-500"
                required
              >
                <option value="">{t("roles.selectModule") ?? "Select module"}</option>
                {Object.entries(modules).map(([key, label]) => (
                  <option key={key} value={key}>{label}</option>
                ))}
              </select>
            </div>
            <div className="flex-1">
              <label className="block text-sm font-medium text-gray-600 dark:text-gray-400 mb-1" htmlFor="page-field-2">{t("roles.fieldAction") ?? "Action"}</label>
              <select id="page-field-2"
                value={action}
                onChange={(e) => setAction(e.target.value)}
                className="w-full px-3 py-2 bg-[#1a1a2e] border border-gray-700 rounded-md text-sm text-gray-200 focus:outline-none focus:border-blue-500"
                required
              >
                <option value="">{t("roles.selectAction") ?? "Select action"}</option>
                {ACTIONS.map((a) => (
                  <option key={a} value={a}>{a === "other" ? "Other (type manually)" : a}</option>
                ))}
              </select>
            </div>
          </div>
          
          {action === "other" && (
            <div>
              <label className="block text-sm font-medium text-gray-600 dark:text-gray-400 mb-1" htmlFor="page-field-3">{t("roles.fieldCustomAction") ?? "Custom Action Name"}</label>
              <input id="page-field-3"
                value={otherAction}
                onChange={(e) => setOtherAction(e.target.value.toLowerCase().replace(/[^a-z]/g, ""))}
                placeholder="e.g., download"
                className="w-full px-3 py-2 bg-[#1a1a2e] border border-gray-700 rounded-md text-sm text-gray-200 focus:outline-none focus:border-blue-500"
                required
              />
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-gray-600 dark:text-gray-400 mb-1" htmlFor="page-field-4">{t("roles.fieldFeatureKey") ?? "Feature Key"}</label>
            <input id="page-field-4"
              value={featureKey}
              readOnly
              className="w-full px-3 py-2 bg-[#1a1a2e] border border-gray-700 rounded-md text-sm text-gray-500 cursor-not-allowed focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-600 dark:text-gray-400 mb-1" htmlFor="page-field-5">{t("roles.fieldDescription")}</label>
            <input id="page-field-5"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="e.g., View analytics dashboard"
              className="w-full px-3 py-2 bg-[#1a1a2e] border border-gray-700 rounded-md text-sm text-gray-200 focus:outline-none focus:border-blue-500"
              required
            />
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-6">
          <button onClick={onClose} disabled={saving} className="px-4 py-2 border border-gray-600 rounded-md text-sm text-gray-400 hover:bg-gray-800 disabled:opacity-50">{t("common.cancel")}</button>
          <button onClick={() => void handleSubmit()} disabled={saving || !featureKey.trim() || !description.trim() || !module || !action || (action === "other" && !otherAction.trim())} className={`px-4 py-2 rounded-md text-sm font-medium text-white ${saving || !featureKey.trim() || !description.trim() || !module || !action || (action === "other" && !otherAction.trim()) ? "bg-gray-600 cursor-default" : "bg-blue-600 hover:bg-blue-700"}`}>
            {saving ? "Creating..." : t("roles.create") ?? "Create"}
          </button>
        </div>
      </div>
    </div>
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
        <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-100 mb-4">{t("roles.modalNew")}</h2>
        {error && <p className="text-sm text-red-400 mb-3">{error}</p>}
        <div className="flex flex-col gap-3">
          <div>
            <label className="block text-sm font-medium text-gray-600 dark:text-gray-400 mb-1" htmlFor="page-field-6">{t("roles.fieldName")}</label>
            <input id="page-field-6" value={name} onChange={(e) => setName(e.target.value)} autoFocus className="w-full px-3 py-2 bg-[#1a1a2e] border border-gray-700 rounded-md text-sm text-gray-800 dark:text-gray-200 focus:outline-none focus:border-blue-500" />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-600 dark:text-gray-400 mb-1" htmlFor="page-field-7">{t("roles.fieldDescription")}</label>
            <input id="page-field-7" value={description} onChange={(e) => setDescription(e.target.value)} className="w-full px-3 py-2 bg-[#1a1a2e] border border-gray-700 rounded-md text-sm text-gray-800 dark:text-gray-200 focus:outline-none focus:border-blue-500" />
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
        <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-100 mb-4">{t("roles.modalEdit")}</h2>
        <div className="flex flex-col gap-3">
          <div>
            <label className="block text-sm font-medium text-gray-600 dark:text-gray-400 mb-1" htmlFor="page-field-8">{t("common.name")}</label>
            <input id="page-field-8" value={name} onChange={(e) => setName(e.target.value)} autoFocus className="w-full px-3 py-2 bg-[#1a1a2e] border border-gray-700 rounded-md text-sm text-gray-800 dark:text-gray-200 focus:outline-none focus:border-blue-500" />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-600 dark:text-gray-400 mb-1" htmlFor="page-field-9">{t("roles.fieldDescription")}</label>
            <input id="page-field-9" value={description} onChange={(e) => setDescription(e.target.value)} className="w-full px-3 py-2 bg-[#1a1a2e] border border-gray-700 rounded-md text-sm text-gray-800 dark:text-gray-200 focus:outline-none focus:border-blue-500" />
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

// ── Lock Password Modal ────────────────────────────────────────────────────────
function LockPasswordModal({ onClose, onSuccess }: { onClose: () => void; onSuccess: () => void }) {
  const { t } = useI18n();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [step, setStep] = useState<"set" | "confirm">("set");

  const handleSubmit = async () => {
    if (step === "set") {
      if (!password.trim()) { setError(t("roles.lockPassRequired") ?? "Password is required"); return; }
      if (password.length < 8) { setError(t("roles.lockPassMinLength") ?? "Password must be at least 8 characters"); return; }
      setStep("confirm");
      setError(null);
      return;
    }
    if (password !== confirm) { setError(t("roles.lockPassMismatch") ?? "Passwords do not match"); return; }
    setSaving(true);
    setError(null);
    try {
      await rolesApi.setLockPassword({ password });
      onSuccess();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to set lock password");
      setSaving(false);
    }
  };

  const handleBack = () => {
    if (step === "confirm") {
      setStep("set");
      setError(null);
    } else {
      onClose();
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
      <div className="w-full max-w-[480px] bg-[#111] rounded-lg border border-gray-800 p-6 shadow-xl">
        <h2 className="text-lg font-semibold text-gray-100 mb-4">{t("roles.lockPasswordTitle") ?? "Set Lock Password"}</h2>
        
        {step === "set" && (
          <div className="mb-4 p-3 bg-amber-900/30 border border-amber-600/40 rounded-md">
            <p className="text-xs text-amber-300">
              <strong>⚠️ Warning:</strong> This lock password cannot be recovered if lost. Store it securely.
              You will need it to modify locked features (including changing other users&apos; passwords).
            </p>
          </div>
        )}
        
        {step === "confirm" && (
          <div className="mb-4 p-3 bg-blue-900/30 border border-blue-600/40 rounded-md">
            <p className="text-xs text-blue-300">
              <strong>Confirm your lock password.</strong> This is your only chance to verify it.
            </p>
          </div>
        )}
        
        {error && <p className="text-sm text-red-400 mb-3">{error}</p>}
        
        <div className="flex flex-col gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-600 dark:text-gray-400 mb-1" htmlFor="page-field-10">
              {step === "set" ? (t("roles.lockPassNew") ?? "New Lock Password") : (t("roles.lockPassConfirm") ?? "Confirm Lock Password")}
            </label>
            <input id="page-field-10"
              type="password"
              value={step === "set" ? password : confirm}
              onChange={(e) => step === "set" ? setPassword(e.target.value) : setConfirm(e.target.value)}
              autoFocus
              disabled={saving}
              className="w-full px-3 py-2 bg-[#1a1a2e] border border-gray-700 rounded-md text-sm text-gray-100 dark:text-gray-200 focus:outline-none focus:border-blue-500 disabled:opacity-50"
              placeholder={step === "set" ? "Enter lock password (min 8 chars)" : "Re-enter lock password"}
            />
          </div>
        </div>
        <div className="flex justify-between gap-2 mt-6">
          <button onClick={handleBack} disabled={saving} className="px-4 py-2 border border-gray-600 rounded-md text-sm text-gray-400 hover:bg-gray-800 disabled:opacity-50">
            {step === "confirm" ? (t("common.back") ?? "Back") : (t("common.cancel") ?? "Cancel")}
          </button>
          <button onClick={() => void handleSubmit()} disabled={saving || (step === "set" ? !password.trim() : !confirm.trim())} className={`px-4 py-2 rounded-md text-sm font-medium text-white ${saving || (step === "set" ? !password.trim() : !confirm.trim()) ? "bg-gray-600 cursor-default" : "bg-green-600 hover:bg-green-700"}`}>
            {saving ? "Setting..." : (step === "set" ? (t("common.next") ?? "Next") : (t("roles.lockPasswordSet") ?? "Set Lock Password"))}
          </button>
        </div>
      </div>
    </div>
  );
}
