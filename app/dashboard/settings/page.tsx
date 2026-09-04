"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, useCallback } from "react";

import { DashboardLayout } from "@/components/DashboardLayout";
import { useAuthStore, useCan } from "@/stores/authStore";
import { useI18n } from "@/components/I18nProvider";
import { listSettings, updateSetting } from "@/lib/api/settings";
import type { SystemSettingRead } from "@/types/contracts";
import { Plug, Plus, X, Check, Loader2, Trash2 } from "lucide-react";
import { api } from "@/lib/api";

interface Integration {
  id: string;
  provider_name: string;
  is_active: number;
  base_url: string | null;
  created_at: string | null;
}

export default function SettingsPage() {
  const router = useRouter();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const canRead = useCan("inventory.read");
  const canWrite = useCan("inventory.write");
  const canManage = useCan("settings.manage");
  const { t } = useI18n();

  const [settings, setSettings] = useState<SystemSettingRead[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");
  const [saving, setSaving] = useState(false);

  // Integrations state
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [showAddIntegration, setShowAddIntegration] = useState(false);
  const [integForm, setIntegForm] = useState({ provider_name: "", api_key: "", base_url: "" });
  const [integSaving, setIntegSaving] = useState(false);

  const loadSettings = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listSettings();
      setSettings(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load settings");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadIntegrations = useCallback(async () => {
    try {
      const res = await api.get("/api/v1/integrations");
      setIntegrations(res.data);
    } catch {
      // silently fail — integrations are optional
    }
  }, []);

  useEffect(() => {
    if (!isAuthenticated()) router.replace("/login");
  }, [isAuthenticated, router]);

  useEffect(() => {
    if (!canRead) return;
    loadSettings();
    loadIntegrations();
  }, [canRead, loadSettings, loadIntegrations]);

  function startEdit(s: SystemSettingRead) {
    setEditingKey(s.key);
    setEditValue(s.value ?? "");
  }

  async function saveEdit() {
    if (!editingKey) return;
    setSaving(true);
    setError(null);
    try {
      await updateSetting(editingKey, editValue);
      setSettings((prev) => prev.map((s) => s.key === editingKey ? { ...s, value: editValue } : s));
      setEditingKey(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to save setting");
    } finally {
      setSaving(false);
    }
  }

  async function handleAddIntegration() {
    if (!integForm.provider_name || !integForm.api_key) return;
    setIntegSaving(true);
    try {
      await api.post("/api/v1/integrations", integForm);
      setShowAddIntegration(false);
      setIntegForm({ provider_name: "", api_key: "", base_url: "" });
      await loadIntegrations();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to save integration");
    } finally {
      setIntegSaving(false);
    }
  }

  return (
    <DashboardLayout>
      <h1 className="text-2xl font-bold text-gray-100 mb-6">{t("settings.title")}</h1>

      {error && (
        <div className="bg-red-900/30 text-red-400 border border-red-600/40 px-4 py-3 rounded-lg mb-4 flex items-center justify-between">
          {error}
          <button onClick={() => setError(null)}><X className="w-4 h-4" /></button>
        </div>
      )}

      {loading ? (
        <p className="text-gray-400">{t("settings.loading")}</p>
      ) : settings.length === 0 ? (
        <p className="text-gray-400">{t("settings.noSettings")}</p>
      ) : (
        <div className="bg-[#111] rounded-lg border border-gray-800 overflow-hidden mb-8">
          <table className="w-full">
            <thead>
              <tr className="border-b border-gray-800">
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-400 uppercase tracking-wider">{t("settings.colKey")}</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-400 uppercase tracking-wider">{t("settings.colValue")}</th>
                {canWrite && <th className="px-4 py-3" />}
              </tr>
            </thead>
            <tbody>
              {settings.map((s) => (
                <tr key={s.key} className="border-b border-gray-800/50 hover:bg-white/5">
                  <td className="px-4 py-3 text-sm font-mono text-gray-300">{s.key}</td>
                  <td className="px-4 py-3 text-sm text-gray-400">
                    {editingKey === s.key ? (
                      <input
                        value={editValue}
                        onChange={(e) => setEditValue(e.target.value)}
                        autoFocus
                        className="w-full px-2 py-1 bg-[#1a1a2e] border border-gray-700 rounded text-gray-200 text-sm focus:outline-none focus:border-blue-500"
                      />
                    ) : (
                      <span className="block max-w-xs truncate">{s.value ?? "—"}</span>
                    )}
                  </td>
                  {canWrite && (
                    <td className="px-4 py-3 whitespace-nowrap">
                      {editingKey === s.key ? (
                        <div className="flex gap-1">
                          <button onClick={() => void saveEdit()} disabled={saving} className="px-2 py-1 text-xs bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50">
                            {saving ? "..." : t("common.save")}
                          </button>
                          <button onClick={() => setEditingKey(null)} className="px-2 py-1 text-xs border border-gray-600 text-gray-400 rounded hover:bg-gray-800">
                            {t("common.cancel")}
                          </button>
                        </div>
                      ) : (
                        <button onClick={() => startEdit(s)} className="text-xs text-blue-400 hover:text-blue-300 underline">
                          {t("common.edit")}
                        </button>
                      )}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ── Third-Party Integrations ──────────────────────────────────────── */}
      <div className="mt-8">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Plug className="w-5 h-5 text-purple-400" />
            <h2 className="text-lg font-bold text-gray-100">Third-Party Integrations</h2>
          </div>
          {canManage && (
            <button
              onClick={() => setShowAddIntegration(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-purple-600 hover:bg-purple-700 text-white text-xs rounded-md transition-colors"
            >
              <Plus className="w-3.5 h-3.5" /> Add Integration
            </button>
          )}
        </div>

        {integrations.length === 0 ? (
          <p className="text-gray-500 text-sm">No integrations configured.</p>
        ) : (
          <div className="bg-[#111] rounded-lg border border-gray-800 overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-800">
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-400 uppercase">Provider</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-400 uppercase">Base URL</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-400 uppercase">Status</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-400 uppercase">Created</th>
                </tr>
              </thead>
              <tbody>
                {integrations.map((integ) => (
                  <tr key={integ.id} className="border-b border-gray-800/50 hover:bg-white/5">
                    <td className="px-4 py-3 text-sm text-gray-200 font-medium">{integ.provider_name}</td>
                    <td className="px-4 py-3 text-sm text-gray-400 font-mono">{integ.base_url || "—"}</td>
                    <td className="px-4 py-3">
                      <span className={`text-xs px-2 py-0.5 rounded-full ${integ.is_active ? "bg-green-900/30 text-green-400" : "bg-gray-800 text-gray-500"}`}>
                        {integ.is_active ? "Active" : "Inactive"}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-500">
                      {integ.created_at ? new Date(integ.created_at).toLocaleDateString() : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Add Integration Modal */}
        {showAddIntegration && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
            <div className="bg-[#1a1a2e] border border-gray-700 rounded-xl p-6 w-full max-w-md shadow-2xl">
              <div className="flex items-center justify-between mb-5">
                <h2 className="text-lg font-bold text-gray-100">Add Integration</h2>
                <button onClick={() => setShowAddIntegration(false)}><X className="w-5 h-5 text-gray-400" /></button>
              </div>
              <div className="space-y-3">
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Provider Name</label>
                  <input
                    className="w-full bg-[#0d0d20] border border-gray-700 rounded-md px-3 py-2 text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500 text-sm"
                    placeholder="e.g. drug_evaluate"
                    value={integForm.provider_name}
                    onChange={(e) => setIntegForm((f) => ({ ...f, provider_name: e.target.value }))}
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-400 mb-1">API Key</label>
                  <input
                    type="password"
                    className="w-full bg-[#0d0d20] border border-gray-700 rounded-md px-3 py-2 text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500 text-sm"
                    placeholder="Bearer token or API key"
                    value={integForm.api_key}
                    onChange={(e) => setIntegForm((f) => ({ ...f, api_key: e.target.value }))}
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Base URL (optional)</label>
                  <input
                    className="w-full bg-[#0d0d20] border border-gray-700 rounded-md px-3 py-2 text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500 text-sm"
                    placeholder="https://api.example.com"
                    value={integForm.base_url}
                    onChange={(e) => setIntegForm((f) => ({ ...f, base_url: e.target.value }))}
                  />
                </div>
              </div>
              <div className="flex gap-3 mt-5">
                <button onClick={() => setShowAddIntegration(false)} className="flex-1 py-2 border border-gray-700 text-gray-300 hover:bg-gray-800 rounded-md text-sm">Cancel</button>
                <button
                  onClick={() => void handleAddIntegration()}
                  disabled={integSaving || !integForm.provider_name || !integForm.api_key}
                  className="flex-1 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-md text-sm font-medium disabled:opacity-50 flex items-center justify-center gap-2"
                >
                  {integSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
                  Save Integration
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
