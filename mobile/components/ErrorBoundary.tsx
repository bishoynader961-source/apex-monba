// ── Global Error Boundary (Blueprint Task 3, Step 3.1) ───────────────────────
// SECURITY:
//   * The boundary is the LAST line of defense: it classifies the error,
//     persists ONLY the classified code (never error.message), and hands the
//     user a recovery screen. Raw exception text never reaches the UI or disk
//     (invariant #7).
//   * No third-party crash SDK is wired in; reports stay on-device until the
//     user explicitly shares them (invariant #2, Point 3.3).

import React from "react";
import { MobileRecoveryScreen } from "../screens/MobileRecoveryScreen";
import { classifyError, writeCrashLog, type ErrorCategory } from "../lib/diagnostics/classifier";

interface ErrorBoundaryProps {
  children: React.ReactNode;
}

interface ErrorBoundaryState {
  category: ErrorCategory | null;
  code: string | null;
}

export class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { category: null, code: null };

  static getDerivedStateFromError(error: unknown): ErrorBoundaryState {
    // Classification is synchronous so the very first recovery render
    // already shows the right category-specific guidance.
    const { category, code } = classifyError(error);
    return { category, code };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo): void {
    // Persist AFTER state is set: even if storage hangs, the user already
    // sees the recovery screen.
    const { category, code } = classifyError(error);
    void writeCrashLog({
      category,
      code,
      timestamp: new Date().toISOString(),
      appVersion: "1.0.0", // kept in sync with app.json version
      platform: "react-native",
    });
  }

  render() {
    if (this.state.code) {
      return (
        <MobileRecoveryScreen
          code={this.state.code}
          category={this.state.category ?? "unknown"}
        />
      );
    }
    return this.props.children;
  }
}
