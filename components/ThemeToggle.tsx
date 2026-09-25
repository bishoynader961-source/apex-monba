"use client";

import { useUiStore } from "@/stores/uiStore";
import { useI18n } from "@/components/I18nProvider";

export function ThemeToggle() {
  const { theme, toggleTheme } = useUiStore();
  const { t } = useI18n();

  return (
    <button
      onClick={toggleTheme}
      title={theme === "dark" ? (t("theme.light") ?? "Light mode") : (t("theme.dark") ?? "Dark mode")}
      style={{
        display: "flex", alignItems: "center", justifyContent: "center",
        width: 32, height: 32, borderRadius: 6, border: "1px solid var(--border)",
        background: "var(--bg-input)", color: "var(--fg)", cursor: "pointer",
        fontSize: 16, transition: "background 0.2s",
      }}
    >
      {theme === "dark" ? "☀️" : "🌙"}
    </button>
  );
}
