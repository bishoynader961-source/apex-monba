"use client";

import React from "react";
import { useUiStore } from "@/stores/uiStore";

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
  errorInfo: React.ErrorInfo | null;
}

interface ErrorBoundaryProps {
  children: React.ReactNode;
  fallback?: React.ReactNode;
}

export class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error, errorInfo: null };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    this.setState({ error, errorInfo });

    // Log to console for immediate debugging
    if (process.env.NODE_ENV !== "production") {
      console.error("[ErrorBoundary] Caught error:", error);
      console.error("[ErrorBoundary] Component stack:", errorInfo.componentStack);
    }

    const payload = {
      error_type: error.name,
      error_message: error.message,
      stack_trace: error.stack?.slice(0, 4000) || null,
      component_stack: errorInfo.componentStack?.slice(0, 2000) || null,
      url: typeof window !== "undefined" ? window.location.href : null,
      user_agent: typeof navigator !== "undefined" ? navigator.userAgent : null,
      app_version: process.env.NEXT_PUBLIC_APP_VERSION || "1.0.0",
      timestamp: new Date().toISOString(),
    };

    fetch("/api/v1/crash-report", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${localStorage.getItem("access_token") || ""}`,
      },
      body: JSON.stringify(payload),
    }).catch(() => {});
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null, errorInfo: null });
  };

  handleCopyError = () => {
    const { error, errorInfo } = this.state;
    const errorDetails = [
      `Error: ${error?.name}: ${error?.message}`,
      `Stack: ${error?.stack}`,
      `Component Stack: ${errorInfo?.componentStack}`,
      `URL: ${typeof window !== "undefined" ? window.location.href : "N/A"}`,
      `Time: ${new Date().toISOString()}`,
    ].join("\n\n");

    navigator.clipboard.writeText(errorDetails).then(() => {
      useUiStore.getState().showToast("Error details copied to clipboard", "success");
    }).catch(() => {
      useUiStore.getState().showToast("Failed to copy to clipboard", "error");
    });
  };

  handleReturnToDashboard = () => {
    if (typeof window !== "undefined") {
      window.location.href = "/dashboard";
    }
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;

      const error = this.state.error;
      const componentStack = this.state.errorInfo?.componentStack;

      return (
        <div className="min-h-[400px] flex items-center justify-center p-6">
          <div className="bg-white dark:bg-[#1a1a2e] border border-gray-200 dark:border-gray-800 rounded-lg p-6 max-w-2xl w-full text-center">
            <div className="w-12 h-12 rounded-full bg-red-600/20 flex items-center justify-center mx-auto mb-4">
              <span className="text-red-500 text-xl">!</span>
            </div>
            <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-100 mb-2">Something went wrong</h2>
            <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
              An unexpected error occurred. The issue has been logged.
            </p>
            {error && (
              <div className="text-left mb-4 p-3 bg-gray-900 border border-gray-700 rounded text-xs font-mono text-red-400 max-h-40 overflow-auto">
                <strong>Error: </strong>{error.name}: {error.message}
              </div>
            )}
            {componentStack && (
              <details className="text-left mb-4">
                <summary className="text-xs text-gray-500 cursor-pointer mb-2">Show Component Stack</summary>
                <pre className="text-xs text-gray-400 bg-gray-900 p-3 rounded border border-gray-700 max-h-60 overflow-auto text-left">
                  {componentStack}
                </pre>
              </details>
            )}
            <div className="flex flex-col sm:flex-row gap-2 justify-center">
              <button
                onClick={this.handleCopyError}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md font-medium transition-colors text-sm"
              >
                Copy error details
              </button>
              <button
                onClick={this.handleReturnToDashboard}
                className="px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-md font-medium transition-colors text-sm"
              >
                Return to Dashboard
              </button>
              <button
                onClick={this.handleReset}
                className="px-4 py-2 border border-gray-600 hover:bg-gray-800 text-gray-300 rounded-md font-medium transition-colors text-sm"
              >
                Try Again
              </button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
