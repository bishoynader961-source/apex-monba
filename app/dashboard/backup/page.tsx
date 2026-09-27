"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, useCallback, useRef } from "react";

import { useI18n } from "@/components/I18nProvider";
import { DashboardLayout } from "@/components/DashboardLayout";
import { useAuthStore, useCan } from "@/stores/authStore";
import {
  createBackup,
  createEncryptedBackup,
  listBackups,
  restoreBackup,
  restoreEncryptedBackup,
  type BackupEntry,
} from "@/lib/api/admin";
import { RouteGuard } from "@/components/RouteGuard";
import type { BackupResult } from "@/types/contracts";

const SECTION_STYLE = {
  background: "var(--bg-card)",
  border: "1px solid var(--border)",
  borderRadius: 8,
  padding: 20,
  marginBottom: 20,
};

export default function BackupPage() {
  const { t } = useI18n();
  const router = useRouter();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const canRead = useCan("backup.read");
const canWrite = useCan("backup.create");
  const fileRef = useRef<HTMLInputElement>(null);

  const [backing, setBacking] = useState(false);
  const [result, setResult] = useState<BackupResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [backups, setBackups] = useState<BackupEntry[]>([]);
  const [loadingList, setLoadingList] = useState(true);
  const [restoring, setRestoring] = useState(false);

  // Sprint 2A: encrypted backup state. The recovery key is displayed ONCE and
  // never persisted — leaving the page (or copying another backup) clears it.
  const [encBacking, setEncBacking] = useState(false);
  const [recoveryKey, setRecoveryKey] = useState<string | null>(null);
  const [encFile, setEncFile] = useState<File | null>(null);
  const [encKey, setEncKey] = useState("");
  const [encRestoring, setEncRestoring] = useState(false);
  const encFileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!isAuthenticated()) router.replace("/login");
  }, [isAuthenticated, router]);

  const loadBackups = useCallback(async () => {
    setLoadingList(true);
    try {
      const data = await listBackups();
      setBackups(data);
    } catch {
      setBackups([]);
    } finally {
      setLoadingList(false);
    }
  }, []);

  useEffect(() => {
    if (isAuthenticated()) void loadBackups();
  }, [isAuthenticated, loadBackups]);

  async function handleBackup() {
    setBacking(true);
    setError(null);
    setResult(null);
    try {
      const res = await createBackup();
      setResult(res);
      void loadBackups();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Backup failed");
    } finally {
      setBacking(false);
    }
  }

  async function handleEncryptedBackup() {
    setEncBacking(true);
    setError(null);
    try {
      const res = await createEncryptedBackup();
      setRecoveryKey(res.recovery_key); // shown ONCE; never persisted
      void loadBackups();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Encrypted backup failed");
    } finally {
      setEncBacking(false);
    }
  }

  async function handleEncryptedRestore() {
    if (!encFile) return;
    if (!confirm("This will replace the current database from the encrypted backup. Are you sure?")) return;
    setEncRestoring(true);
    setError(null);
    try {
      const res = await restoreEncryptedBackup(encFile, encKey.trim());
      alert(res.message);
      setEncFile(null);
      setEncKey("");
      if (encFileRef.current) encFileRef.current.value = "";
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Encrypted restore failed");
    } finally {
      setEncRestoring(false);
    }
  }

  async function handleRestore(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!confirm("This will replace the current database. Are you sure?")) return;
    setRestoring(true);
    setError(null);
    try {
      const res = await restoreBackup(file);
      alert(res.message);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Restore failed");
    } finally {
      setRestoring(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  return (
    <DashboardLayout>
      <RouteGuard permission="backup.read">
      <h1 style={{ fontSize: 22, fontWeight: 700, color: "var(--fg)", marginBottom: 20 }}>{t("backup.title")}</h1>

      {error && (
        <div style={{ background: "var(--bg-card)", border: "1px solid var(--danger)", color: "var(--danger)", padding: "10px 16px", borderRadius: 8, marginBottom: 16 }}>
          {error}
        </div>
      )}

      {result && (
        <div style={{ background: "var(--bg-card)", border: "1px solid var(--success)", color: "var(--success)", padding: "10px 16px", borderRadius: 8, marginBottom: 16 }}>
          {t("backup.success")} — {(result.size_bytes / 1024).toFixed(1)} KB
        </div>
      )}

      {/* Create Backup */}
      <div style={SECTION_STYLE}>
        <h2 style={{ fontSize: 16, fontWeight: 600, color: "var(--fg)", marginBottom: 8 }}>Create Backup</h2>
        <p style={{ fontSize: 13, color: "var(--fg-muted)", marginBottom: 12 }}>{t("backup.description")}</p>
        <button
          onClick={() => void handleBackup()}
          disabled={backing || !canWrite}
          style={{
            padding: "8px 20px", fontSize: 13, fontWeight: 600, borderRadius: 6, border: "none", cursor: backing || !canWrite ? "default" : "pointer",
            background: backing ? "var(--bg-hover)" : "var(--danger)", color: "#fff", opacity: backing || !canWrite ? 0.6 : 1,
          }}
        >
          {backing ? t("backup.creating") : t("backup.createBackup")}
        </button>
      </div>

      {/* Encrypted Backup (Sprint 2A) */}
      <div style={SECTION_STYLE}>
        <h2 style={{ fontSize: 16, fontWeight: 600, color: "var(--fg)", marginBottom: 8 }}>Encrypted Backup</h2>
        <p style={{ fontSize: 13, color: "var(--fg-muted)", marginBottom: 12 }}>
          Creates an AES-256 encrypted snapshot (.backup.enc). The decryption key is
          shown once and never stored — keep it somewhere safe.
        </p>
        <button
          onClick={() => void handleEncryptedBackup()}
          disabled={encBacking || !canWrite}
          style={{
            padding: "8px 20px", fontSize: 13, fontWeight: 600, borderRadius: 6, border: "none", cursor: encBacking || !canWrite ? "default" : "pointer",
            background: encBacking ? "var(--bg-hover)" : "var(--primary)", color: "var(--primary-fg, #fff)", opacity: encBacking || !canWrite ? 0.6 : 1,
          }}
        >
          {encBacking ? "Encrypting..." : "Create Encrypted Backup"}
        </button>

        {recoveryKey && (
          <div style={{ marginTop: 16, padding: 16, borderRadius: 8, border: "1px solid var(--warning, #d97706)", background: "rgba(217, 119, 6, 0.08)" }}>
            <p style={{ fontSize: 14, fontWeight: 700, color: "var(--warning, #d97706)", margin: 0 }}>
              ⚠️ Save this key — you cannot recover your backup without it
            </p>
            <code style={{ display: "block", marginTop: 8, padding: "8px 12px", borderRadius: 6, background: "var(--bg-input)", fontFamily: "monospace", fontSize: 13, wordBreak: "break-all", color: "var(--fg)" }}>
              {recoveryKey}
            </code>
            <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
              <button
                onClick={() => void navigator.clipboard.writeText(recoveryKey)}
                style={{ padding: "6px 14px", fontSize: 12, borderRadius: 6, border: "1px solid var(--border)", background: "var(--bg-input)", color: "var(--fg)", cursor: "pointer" }}
              >
                Copy key
              </button>
              <button
                onClick={() => setRecoveryKey(null)}
                style={{ padding: "6px 14px", fontSize: 12, borderRadius: 6, border: "1px solid var(--border)", background: "transparent", color: "var(--fg-muted)", cursor: "pointer" }}
              >
                I&apos;ve saved it — hide forever
              </button>
            </div>
          </div>
        )}

        <div style={{ borderTop: "1px solid var(--border)", marginTop: 16, paddingTop: 12 }}>
          <p style={{ fontSize: 13, color: "var(--fg-muted)", marginBottom: 8 }}>
            Restore an encrypted backup: choose the .backup.enc file and enter its key.
          </p>
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <label
              style={{
                padding: "8px 16px", fontSize: 13, fontWeight: 600, borderRadius: 6, border: "1px solid var(--border)",
                background: "var(--bg-input)", color: "var(--fg)", cursor: encRestoring ? "default" : "pointer", display: "inline-block",
              }}
            >
              {encFile ? encFile.name : "Choose .backup.enc file"}
              <input
                ref={encFileRef}
                type="file"
                accept=".backup.enc"
                className="hidden"
                disabled={encRestoring}
                onChange={(e) => setEncFile(e.target.files?.[0] ?? null)}
              />
            </label>
            <input
              value={encKey}
              onChange={(e) => setEncKey(e.target.value)}
              placeholder="64-character recovery key"
              style={{ flex: 1, minWidth: 240, padding: "8px 12px", borderRadius: 6, border: "1px solid var(--border)", background: "var(--bg-input)", color: "var(--fg)", fontSize: 13, fontFamily: "monospace" }}
            />
            <button
              onClick={() => void handleEncryptedRestore()}
              disabled={encRestoring || !encFile || encKey.trim().length !== 64}
              style={{
                padding: "8px 20px", fontSize: 13, fontWeight: 600, borderRadius: 6, border: "none", cursor: encRestoring || !encFile || encKey.trim().length !== 64 ? "default" : "pointer",
                background: "var(--danger)", color: "#fff", opacity: encRestoring || !encFile || encKey.trim().length !== 64 ? 0.6 : 1,
              }}
            >
              {encRestoring ? "Restoring..." : "Restore Encrypted"}
            </button>
          </div>
        </div>
      </div>

      {/* Restore Backup */}
      <div style={SECTION_STYLE}>
        <h2 style={{ fontSize: 16, fontWeight: 600, color: "var(--fg)", marginBottom: 8 }}>Restore from Backup</h2>
        <p style={{ fontSize: 13, color: "var(--fg-muted)", marginBottom: 12 }}>
          Upload a .db or .gz backup file to restore the database. This will overwrite the current data.
        </p>
        <label
          style={{
          padding: "8px 20px", fontSize: 13, fontWeight: 600, borderRadius: 6, border: "1px solid var(--border)",
          background: "var(--bg-input)", color: "var(--fg)", cursor: restoring ? "default" : "pointer", display: "inline-block",
        }}
        >
          {restoring ? "Restoring..." : "Choose Backup File"}
          <input ref={fileRef} type="file" accept=".db,.gz" className="hidden" onChange={() => void handleRestore} disabled={restoring} />
        </label>
      </div>

      {/* Backup History */}
      <div style={SECTION_STYLE}>
        <h2 style={{ fontSize: 16, fontWeight: 600, color: "var(--fg)", marginBottom: 12 }}>Backup History</h2>
        {loadingList ? (
          <p style={{ fontSize: 13, color: "var(--fg-muted)" }}>Loading...</p>
        ) : backups.length === 0 ? (
          <p style={{ fontSize: 13, color: "var(--fg-muted)" }}>No backups found.</p>
        ) : (
          <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border)" }}>
                <th style={{ textAlign: "left", padding: "8px 12px", color: "var(--fg-muted)" }}>Filename</th>
                <th style={{ textAlign: "right", padding: "8px 12px", color: "var(--fg-muted)" }}>Size</th>
                <th style={{ textAlign: "right", padding: "8px 12px", color: "var(--fg-muted)" }}>Date</th>
              </tr>
            </thead>
            <tbody>
              {backups.map((b) => (
                <tr key={b.path} style={{ borderBottom: "1px solid var(--border)" }}>
                  <td style={{ padding: "8px 12px", color: "var(--fg)", fontFamily: "monospace", fontSize: 12 }}>{b.filename}</td>
                  <td style={{ padding: "8px 12px", textAlign: "right", color: "var(--fg)" }}>{(b.size_bytes / 1024).toFixed(1)} KB</td>
                  <td style={{ padding: "8px 12px", textAlign: "right", color: "var(--fg-muted)" }}>{new Date(b.modified * 1000).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </RouteGuard>
    </DashboardLayout>
  );
}
