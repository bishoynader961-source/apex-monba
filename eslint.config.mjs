import jsxA11y from "eslint-plugin-jsx-a11y";
import coreWebVitals from "eslint-config-next/core-web-vitals";
import nextTypescript from "eslint-config-next/typescript";

// ESLint 9 flat config for Next.js 16 (App Router) + React 19 + TypeScript.
// `next lint` was removed in Next 16; this restores the lint gate via
// `npm run lint`. eslint-config-next 16 ships native flat configs, so no
// FlatCompat bridging (which crashes circularly on the react plugin).
const eslintConfig = [
  // Global ignores must come first so the presets never see excluded trees.
  {
    ignores: [
      "node_modules/**",
      ".next/**",
      "out/**",
      "build/**",
      "dist/**",
      "next-env.d.ts",
      // Vendored/copied worktrees and archives are not part of the build.
      ".kilo/**",
      "archive/**",
      "src-tauri/target/**",
      // PyInstaller build dirs, deploy artifacts, and the Python venv.
      "tauri-build-target/**",
      ".vercel/**",
      "backend_fastapi/build/**",
      "backend_fastapi/dist/**",
      "venv/**",
      ".venv/**",
      "snapshots/**",
      // Vendored third-party browser bundles served by FastAPI — never modify.
      "backend_fastapi/app/static/**",
      // Python/scratch tooling at the repo root is not lintable JS.
      "*.py",
      "*.cjs",
      "test_label_engine.js",
      "audit_i18n.js",
      "check_repo.py",
      "install.log",
      // Standalone infra scripts (CommonJS by design, run under Node).
      "docker-healthcheck.js",
      "scripts/**",
    ],
  },
  ...coreWebVitals,
  ...nextTypescript,
  {
    // Sprint 3D: dedicated a11y audit scope (the three most-used pages).
    // Critical/Serious rules error; Moderate/Minor stay off the gate and are
    // tracked for the backlog. (The jsx-a11y plugin itself is already
    // registered by eslint-config-next's core-web-vitals preset.)
    files: ["app/pos/page.tsx", "app/dashboard/inventory/page.tsx", "app/rx/page.tsx"],
    rules: {
      ...jsxA11y.configs.recommended.rules,
      // Severity triage (axe mapping): error = Critical/Serious, off = Moderate/Minor.
      "jsx-a11y/alt-text": "error",
      "jsx-a11y/anchor-is-valid": "error",
      "jsx-a11y/aria-activedescendant-has-tabindex": "error",
      "jsx-a11y/aria-props": "error",
      "jsx-a11y/aria-proptypes": "error",
      "jsx-a11y/aria-role": "error",
      "jsx-a11y/aria-unsupported-elements": "error",
      "jsx-a11y/autocomplete-valid": "error",
      "jsx-a11y/heading-has-content": "error",
      "jsx-a11y/iframe-has-title": "error",
      "jsx-a11y/interactive-supports-focus": "error",
      "jsx-a11y/label-has-associated-control": "error",
      "jsx-a11y/media-has-caption": "error",
      "jsx-a11y/mouse-events-have-key-events": "error",
      "jsx-a11y/no-access-key": "error",
      "jsx-a11y/no-aria-hidden-on-focusable": "error",
      "jsx-a11y/no-noninteractive-element-interactions": "off",
      "jsx-a11y/no-noninteractive-tabindex": "off",
      "jsx-a11y/no-redundant-roles": "off",
      "jsx-a11y/no-static-element-interactions": "off",
      "jsx-a11y/role-has-required-aria-props": "error",
      "jsx-a11y/role-supports-aria-props": "error",
      "jsx-a11y/scope": "off",
      "jsx-a11y/tabindex-no-positive": "error",
    },
  },
  {
    // Scoped to JS/TS files (flat configs cannot set rules globally).
    files: ["**/*.{js,jsx,mjs,ts,tsx,mts,cts}"],
    rules: {
      // The codebase predates exhaustive-deps discipline in a few large pages;
      // warnings stay visible without failing the gate.
      "react-hooks/exhaustive-deps": "warn",
      // ── Baseline rules: error → warn for the legacy codebase ──────────
      // These are REAL issues tracked in PROJECT_MAP [ORPHANS & PENDING],
      // but failing the whole gate on day one would hide new regressions.
      // Each needs a surgical fix (conditional-hook refactors in ~8 pages,
      // typed API responses in lib/api, setState-in-effect restructures).
      "@typescript-eslint/no-this-alias": "warn",       // 113 hits, mostly service classes
      "@typescript-eslint/no-explicit-any": "warn",     // 34 hits, lib/api + mobile
      "react-hooks/rules-of-hooks": "warn",             // 93 hits, conditional hooks in dashboard pages
      "react-hooks/set-state-in-effect": "warn",        // 42 hits, React Compiler-era rule
      "react-hooks/immutability": "warn",
      "react-hooks/static-components": "warn",
      "react-hooks/purity": "warn",
      "react-hooks/preserve-manual-memoization": "warn",
      "react-hooks/refs": "warn",
    },
  },
];

export default eslintConfig;
