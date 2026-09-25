"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Lock, Loader2, X } from "lucide-react";
import { useI18n } from "@/components/I18nProvider";
import { useAuthStore } from "@/stores/authStore";
import { api } from "@/lib/api";

interface AuthConfirmModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => Promise<void>;
  title?: string;
  message?: string;
  actionName?: string;
}

export function AuthConfirmModal({
  isOpen,
  onClose,
  onConfirm,
  title,
  message,
  actionName = "action",
}: AuthConfirmModalProps) {
  const { t } = useI18n();
  const router = useRouter();
  const token = useAuthStore((s) => s.token);
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!password) {
      setError(t("authConfirm.passwordRequired"));
      return;
    }
    setLoading(true);
    setError("");

    try {
      await api.post("/api/v1/auth/verify-password", { password });

      await onConfirm();
      setPassword("");
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("authConfirm.verificationFailed"));
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50" onClick={onClose}>
      <div className="w-full max-w-md bg-[#1a1a2e] rounded-lg border border-gray-700 p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-100">{title ?? t("authConfirm.title")}</h2>
          <button
            onClick={onClose}
            disabled={loading}
            className="text-gray-600 dark:text-gray-400 hover:text-gray-200 disabled:opacity-50"
            aria-label="Close"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="mb-4 text-sm text-gray-700 dark:text-gray-300">
          {message ?? t("authConfirm.message", { action: actionName })}
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="confirm-password" className="block text-sm font-medium text-gray-600 dark:text-gray-400 mb-1">
              {t("authConfirm.passwordLabel")}
            </label>
            <input
              id="confirm-password"
              type="password"
              value={password}
              onChange={(e) => { setPassword(e.target.value); setError(""); }}
              placeholder={t("authConfirm.passwordPlaceholder")}
              autoFocus
              disabled={loading}
              className="w-full px-3 py-2 bg-[#111] border border-gray-700 rounded-md text-sm text-gray-800 dark:text-gray-100 focus:outline-none focus:border-blue-500 disabled:opacity-50"
            />
          </div>

          {error && (
            <p className="text-sm text-red-400 flex items-center gap-1">
              <Lock className="w-4 h-4" />
              {error}
            </p>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              disabled={loading}
              className="px-4 py-2 border border-gray-600 rounded-md text-sm text-gray-400 hover:bg-gray-800 disabled:opacity-50"
            >
              {t("common.cancel")}
            </button>
            <button
              type="submit"
              disabled={loading || !password}
              className={`px-4 py-2 rounded-md text-sm font-medium text-white ${
                loading || !password
                  ? "bg-gray-600 cursor-default"
                  : "bg-red-600 hover:bg-red-700"
              }`}
            >
              {loading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin mr-2" />
                  {t("common.verifying")}
                </>
              ) : (
                t("authConfirm.confirmBtn", { action: actionName })
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}