/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./hooks/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
    "./stores/**/*.{ts,tsx}",
    "./types/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "var(--bg-primary)",
        surface: "var(--bg-secondary)",
        primary: {
          DEFAULT: "var(--brand-primary)",
          hover: "var(--brand-primary-hover)",
        },
        sidebar: {
          DEFAULT: "var(--brand-sidebar)",
          hover: "var(--brand-sidebar-hover)",
        },
        textMain: "var(--text-main)",
        textMuted: "var(--text-muted)",
        border: "var(--border)",
        danger: "var(--danger)",
        success: "var(--success)",
        warning: "var(--warning)",
      },
      boxShadow: {
        sm: "var(--shadow-sm)",
        md: "var(--shadow-md)",
      },
    },
  },
  plugins: [],
};
