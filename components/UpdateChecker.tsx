"use client";

import { useState } from "react";
import { useI18n } from "@/components/I18nProvider";

type Phase = "idle" | "checking" | "available" | "downloading" | "installed" | "uptodate" | "error";

/**
 * "Check for Updates" control for the packaged desktop app.
 *
 * Uses the Tauri v2 updater plugin: checks the configured endpoint for a
 * newer version, verifies its Ed25519 signature (enforced by the plugin — an
 * unsigned or wrong-key update is rejected before it ever runs), downloads
 * and installs it, then offers a relaunch.
 *
 * Renders nothing outside the Tauri webview (browser/dev server builds have
 * no updater), so the same Settings page works everywhere.
 */
export function UpdateChecker() {
  const { t } = useI18n();
  const [phase, setPhase] = useState<Phase>("idle");
  const [message, setMessage] = useState("");
  const [version, setVersion] = useState("");

  const isTauri = typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
  if (!isTauri) return null;

  const run = async () => {
    setPhase("checking");
    setMessage("");
    try {
      const { check } = await import("@tauri-apps/plugin-updater");
      const update = await check();
      if (!update) {
        setPhase("uptodate");
        return;
      }
      setVersion(update.version ?? "");
      setPhase("available");
      const { ask } = await import("@tauri-apps/plugin-dialog");
      const yes = await ask(
        `Version ${update.version ?? ""} is available. Download and install it now?`,
        { title: "Update available", kind: "info" },
      );
      if (!yes) {
        setPhase("idle");
        return;
      }
      setPhase("downloading");
      let lastProgress = 0;
      await update.downloadAndInstall((event) => {
        if (event.event === "Started") {
          setMessage("Downloading…");
        } else if (event.event === "Progress") {
          lastProgress += event.data.chunkLength;
          setMessage(`Downloading… ${(lastProgress / 1024 / 1024).toFixed(1)} MB`);
        } else if (event.event === "Finished") {
          setMessage("Install complete.");
        }
      });
      setPhase("installed");
    } catch (err) {
      // Signature failures surface here: the plugin refuses to apply an
      // update whose Ed25519 signature does not match the embedded pubkey.
      setPhase("error");
      setMessage(err instanceof Error ? err.message : String(err));
    }
  };

  const relaunch = async () => {
    const { relaunch } = await import("@tauri-apps/plugin-process");
    await relaunch();
  };

  return (
    <div style={{ marginTop: 12 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <button
          type="button"
          id="check-updates-btn"
          onClick={run}
          disabled={phase === "checking" || phase === "downloading"}
          style={{
            display: "inline-flex", alignItems: "center", gap: 6,
            padding: "7px 16px", borderRadius: 6,
            border: "1px solid var(--border)",
            background: "var(--bg-input, var(--bg-secondary))",
            color: "var(--fg)", fontSize: 13, fontWeight: 500, cursor: "pointer",
          }}
        >
          {phase === "checking" || phase === "downloading" ? "Checking…" : "Check for Updates"}
        </button>
        {message && (
          <span style={{ fontSize: 12, color: "var(--fg-muted)" }}>{message}</span>
        )}
      </div>

      {phase === "uptodate" && (
        <p style={{ marginTop: 6, fontSize: 12, color: "var(--success)" }}>
          You&apos;re up to date.
        </p>
      )}
      {phase === "available" && (
        <p style={{ marginTop: 6, fontSize: 12, color: "var(--fg-muted)" }}>
          Update {version} ready to download.
        </p>
      )}
      {phase === "installed" && (
        <div style={{ marginTop: 8 }}>
          <p style={{ fontSize: 13, color: "var(--success)" }}>
            Installed. Restart the app to finish updating.
          </p>
          <button
            type="button"
            onClick={relaunch}
            style={{
              marginTop: 6, padding: "6px 14px", borderRadius: 6,
              border: "none", background: "var(--brand-primary)", color: "#fff",
              fontSize: 13, fontWeight: 500, cursor: "pointer",
            }}
          >
            Restart now
          </button>
        </div>
      )}
      {phase === "error" && (
        <p style={{ marginTop: 6, fontSize: 12, color: "var(--danger)" }}>
          Update failed: {message}. Updates are cryptographically verified —
          this can happen offline or with a tampered package.
        </p>
      )}
      <p style={{ marginTop: 6, fontSize: 11, color: "var(--fg-muted)" }}>
        Updates are signed and verified before install.
      </p>
    </div>
  );
}
