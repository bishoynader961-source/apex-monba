"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { DashboardLayout } from "@/components/DashboardLayout";
import { useAuthStore, useCan } from "@/stores/authStore";
import { useI18n } from "@/components/I18nProvider";
import { listUsers, getUser, updateUser, setUserActive } from "@/lib/api/users";
import { registerUser } from "@/lib/api/auth";
import { listRoles } from "@/lib/api/roles";
import type { UserPublic } from "@/types/contracts";
import type { RoleRead } from "@/lib/api/roles";

export default function UsersPage() {
  const { t } = useI18n();
  const router = useRouter();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const canRead = useCan("users.read");
  const canWrite = useCan("users.write");

  const [users, setUsers] = useState<UserPublic[]>([]);
  const [roles, setRoles] = useState<RoleRead[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedUser, setSelectedUser] = useState<UserPublic | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);

  const ROLE_NAMES: Record<number, string> = Object.fromEntries(roles.map(r => [r.id, r.name]));

  useEffect(() => {
    if (!isAuthenticated()) router.replace("/login");
  }, [isAuthenticated, router]);

  useEffect(() => {
    if (!canRead) return;
    loadUsers();
    loadRoles();
  }, [canRead]);

  async function loadRoles() {
    try {
      const data = await listRoles();
      setRoles(data);
    } catch { /* ignore */ }
  }

  async function loadUsers() {
    setLoading(true);
    setError(null);
    try {
      const data = await listUsers();
      setUsers(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load users");
    } finally {
      setLoading(false);
    }
  }

  async function viewUser(id: number) {
    try {
      const user = await getUser(id);
      setSelectedUser(user);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load user");
    }
  }

  async function handleToggleActive(user: UserPublic) {
    try {
      const updated = await setUserActive(user.id, !user.is_active);
      setSelectedUser(updated);
      setUsers((prev) => prev.map((u) => u.id === user.id ? updated : u));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to update user");
    }
  }

  async function handleEditSave(displayName: string, roleId: number) {
    if (!selectedUser) return;
    try {
      const updated = await updateUser(selectedUser.id, { display_name: displayName, role_id: roleId });
      setSelectedUser(updated);
      setUsers((prev) => prev.map((u) => u.id === selectedUser.id ? updated : u));
      setEditOpen(false);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to update user");
    }
  }

  return (
    <DashboardLayout>
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-2xl font-bold text-gray-100">{t("users.title")}</h1>
        {canWrite && (
          <button onClick={() => setCreateOpen(true)} className="px-4 py-2 bg-green-600 text-white rounded-md text-sm font-medium hover:bg-green-700">
            {t("users.newUser")}
          </button>
        )}
      </div>

      {error && (
        <div className="bg-red-900/30 text-red-400 border border-red-600/40 px-4 py-3 rounded-lg mb-4">
          {error}
        </div>
      )}

      {loading ? (
        <p className="text-gray-400">{t("users.loading")}</p>
      ) : (
        <div className="flex gap-6">
          <div className="flex-[2] bg-[#111] rounded-lg border border-gray-800 overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-800">
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-400 uppercase tracking-wider">{t("users.colId")}</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-400 uppercase tracking-wider">{t("users.colUsername")}</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-400 uppercase tracking-wider">{t("users.colDisplayName")}</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-400 uppercase tracking-wider">{t("users.colRoleId")}</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-400 uppercase tracking-wider">{t("users.colStatus")}</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-400 uppercase tracking-wider">Actions</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id} className={`border-b border-gray-800/50 ${selectedUser?.id === u.id ? "bg-blue-900/20" : "hover:bg-white/5"}`}>
                    <td className="px-4 py-3 text-sm text-gray-300">{u.id}</td>
                    <td className="px-4 py-3 text-sm font-medium text-gray-200">{u.username}</td>
                    <td className="px-4 py-3 text-sm text-gray-400">{u.display_name}</td>
                    <td className="px-4 py-3 text-sm text-gray-400">{ROLE_NAMES[u.role_id] ?? `Role ${u.role_id}`}</td>
                    <td className="px-4 py-3">
                      <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${u.is_active ? "bg-green-900/30 text-green-400" : "bg-red-900/30 text-red-400"}`}>
                        {u.is_active ? t("users.statusActive") : t("users.statusInactive")}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <button onClick={() => viewUser(u.id)} className="text-sm text-blue-400 hover:text-blue-300 underline">
                        {t("users.view")}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {selectedUser && (
            <div className="flex-1 bg-[#111] rounded-lg border border-gray-800 p-5 self-start">
              <h2 className="text-base font-semibold text-gray-100 mb-3">{t("users.userDetails")}</h2>
              <dl className="text-sm">
                {[
                  [t("users.colId"), selectedUser.id],
                  [t("users.labelUsername"), selectedUser.username],
                  [t("users.labelDisplayName"), selectedUser.display_name],
                  [t("users.labelRole"), ROLE_NAMES[selectedUser.role_id] ?? `Role ${selectedUser.role_id}`],
                  [t("users.labelActive"), selectedUser.is_active ? t("users.yes") : t("users.no")],
                  [t("users.labelCreated"), selectedUser.created_at ?? "—"],
                ].map(([label, value]) => (
                  <div key={String(label)} className="flex justify-between py-1.5 border-b border-gray-800/50">
                    <dt className="text-gray-400">{String(label)}</dt>
                    <dd className="font-medium text-gray-200">{String(value)}</dd>
                  </div>
                ))}
              </dl>
              {canWrite && (
                <div className="flex gap-2 mt-3">
                  <button onClick={() => setEditOpen(true)} className="px-3 py-1.5 text-xs bg-blue-600 text-white rounded hover:bg-blue-700">
                    {t("users.edit")}
                  </button>
                  <button
                    onClick={() => void handleToggleActive(selectedUser)}
                    className={`px-3 py-1.5 text-xs text-white rounded ${selectedUser.is_active ? "bg-red-600 hover:bg-red-700" : "bg-green-600 hover:bg-green-700"}`}
                  >
                    {selectedUser.is_active ? t("users.deactivate") : t("users.activate")}
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {createOpen && (
        <CreateUserModal
          roles={roles}
          onClose={() => setCreateOpen(false)}
          onSuccess={() => {
            void loadUsers();
            setCreateOpen(false);
          }}
        />
      )}

      {editOpen && selectedUser && (
        <EditUserModal
          user={selectedUser}
          roles={roles}
          onClose={() => setEditOpen(false)}
          onSave={handleEditSave}
        />
      )}
    </DashboardLayout>
  );
}

// ── Create User Modal ────────────────────────────────────────────────────────

function CreateUserModal({ roles, onClose, onSuccess }: { roles: RoleRead[]; onClose: () => void; onSuccess: () => void }) {
  const { t } = useI18n();
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [roleId, setRoleId] = useState(3);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    if (!username.trim() || !password) { setError("Username and password are required"); return; }
    if (password.length < 8) { setError("Password must be at least 8 characters"); return; }
    setSaving(true);
    setError(null);
    try {
      await registerUser({
        username: username.trim(),
        display_name: displayName.trim() || undefined,
        password,
        role_id: roleId,
      });
      onSuccess();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Create failed");
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
      <div className="w-full max-w-[400px] bg-[#111] rounded-lg border border-gray-800 p-6 shadow-xl">
        <h2 className="text-lg font-semibold text-gray-100 mb-4">{t("users.modalNew")}</h2>
        {error && <p className="text-sm text-red-400 mb-3">{error}</p>}
        <div className="flex flex-col gap-3">
          <div>
            <label className="block text-sm font-medium text-gray-400 mb-1">{t("users.fieldUsername")}</label>
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="jdoe"
              autoFocus
              className="w-full px-3 py-2 bg-[#1a1a2e] border border-gray-700 rounded-md text-sm text-gray-200 focus:outline-none focus:border-blue-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-400 mb-1">{t("users.fieldDisplayName")}</label>
            <input
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="John Doe"
              className="w-full px-3 py-2 bg-[#1a1a2e] border border-gray-700 rounded-md text-sm text-gray-200 focus:outline-none focus:border-blue-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-400 mb-1">{t("users.fieldPassword")}</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="min 8 characters"
              className="w-full px-3 py-2 bg-[#1a1a2e] border border-gray-700 rounded-md text-sm text-gray-200 focus:outline-none focus:border-blue-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-400 mb-1">{t("users.fieldRole")}</label>
            <select
              value={roleId}
              onChange={(e) => setRoleId(Number(e.target.value))}
              className="w-full px-3 py-2 bg-[#1a1a2e] border border-gray-700 rounded-md text-sm text-gray-200 focus:outline-none focus:border-blue-500"
            >
              {roles.map(r => (
                <option key={r.id} value={r.id}>{r.name}</option>
              ))}
            </select>
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-5">
          <button onClick={onClose} disabled={saving} className="px-4 py-2 border border-gray-600 rounded-md text-sm text-gray-400 hover:bg-gray-800 disabled:opacity-50">
            {t("common.cancel")}
          </button>
          <button onClick={() => void handleSubmit()} disabled={saving || !username.trim() || !password} className={`px-4 py-2 rounded-md text-sm font-medium text-white ${saving || !username.trim() || !password ? "bg-gray-600 cursor-default" : "bg-green-600 hover:bg-green-700"}`}>
            {saving ? "..." : t("users.createUser")}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Edit User Modal ──────────────────────────────────────────────────────────

function EditUserModal({ user, roles, onClose, onSave }: { user: UserPublic; roles: RoleRead[]; onClose: () => void; onSave: (displayName: string, roleId: number) => Promise<void> }) {
  const { t } = useI18n();
  const [displayName, setDisplayName] = useState(user.display_name);
  const [roleId, setRoleId] = useState(user.role_id);
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    try {
      await onSave(displayName, roleId);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
      <div className="w-full max-w-[400px] bg-[#111] rounded-lg border border-gray-800 p-6 shadow-xl">
        <h2 className="text-lg font-semibold text-gray-100 mb-4">{t("users.modalEdit").replace("{username}", user.username)}</h2>
        <div className="flex flex-col gap-3">
          <div>
            <label className="block text-sm font-medium text-gray-400 mb-1">{t("users.labelDisplayName")}</label>
            <input
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              autoFocus
              className="w-full px-3 py-2 bg-[#1a1a2e] border border-gray-700 rounded-md text-sm text-gray-200 focus:outline-none focus:border-blue-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-400 mb-1">{t("users.labelRole")}</label>
            <select
              value={roleId}
              onChange={(e) => setRoleId(Number(e.target.value))}
              className="w-full px-3 py-2 bg-[#1a1a2e] border border-gray-700 rounded-md text-sm text-gray-200 focus:outline-none focus:border-blue-500"
            >
              {roles.map(r => (
                <option key={r.id} value={r.id}>{r.name}</option>
              ))}
            </select>
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-5">
          <button onClick={onClose} disabled={saving} className="px-4 py-2 border border-gray-600 rounded-md text-sm text-gray-400 hover:bg-gray-800 disabled:opacity-50">
            {t("common.cancel")}
          </button>
          <button onClick={() => void handleSave()} disabled={saving} className="px-4 py-2 rounded-md text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-50">
            {saving ? "..." : t("common.save")}
          </button>
        </div>
      </div>
    </div>
  );
}
