"use client";

import { useEffect } from "react";
import { useToast } from "@/hooks/useToast";
import { X } from "lucide-react";

export function Toaster() {
  const { toasts, dismiss } = useToast();

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 pointer-events-none">
      {toasts.map((t) => (
        <ToastItem key={t.id} toast={t} onDismiss={dismiss} />
      ))}
    </div>
  );
}

function ToastItem({ toast, onDismiss }: { toast: { id: string; title: string; message?: string; variant?: "default" | "destructive" | "success" }; onDismiss: (id: string) => void }) {
  useEffect(() => {
    const timer = setTimeout(() => onDismiss(toast.id), 5000);
    return () => clearTimeout(timer);
  }, [toast.id, onDismiss]);

  const baseStyles = "pointer-events-auto flex items-start gap-3 px-4 py-3 rounded-lg shadow-lg min-w-[280px] max-w-[400px] animate-fade-in-up";
  const variantStyles = {
    default: "bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-gray-900 dark:text-gray-100",
    destructive: "bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-red-900 dark:text-red-100",
    success: "bg-green-50 dark:bg-green-900/30 border border-green-200 dark:border-green-800 text-green-900 dark:text-green-100",
  };

  return (
    <div className={`${baseStyles} ${variantStyles[toast.variant ?? "default"]}`} role="alert">
      <div className="flex-1">
        <div className="font-medium text-sm">{toast.title}</div>
        {toast.message && <div className="text-sm opacity-90 mt-0.5">{toast.message}</div>}
      </div>
      <button
        onClick={() => onDismiss(toast.id)}
        className="flex-shrink-0 text-current opacity-50 hover:opacity-100 transition-opacity"
        aria-label="Dismiss"
      >
        <X className="w-4 h-4" />
      </button>
    </div>
  );
}