"use client";

import { useRouter } from "next/navigation";
import { useActionState, useEffect, useState } from "react";

import { loginAction } from "@/app/login/actions";
import { useAuthStore } from "@/stores/authStore";
import { useI18n } from "@/components/I18nProvider";

export default function LoginPage() {
  const router = useRouter();
  const [state, formAction, isPending] = useActionState(loginAction, null);
  const setToken = useAuthStore((s) => s.setToken);
  const fetchCurrentUser = useAuthStore((s) => s.fetchCurrentUser);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const token = useAuthStore((s) => s.token);
  const { t } = useI18n();

  const [setupComplete, setSetupComplete] = useState(false);

  // Check setup status on load
  useEffect(() => {
    if (typeof window !== "undefined" && window.location.search.includes("setup=complete")) {
      setSetupComplete(true);
    }
    const checkSetup = async () => {
      try {
        const res = await fetch("/api/v1/setup/status");
        if (res.ok) {
          const data = await res.json();
          if (data.setup_required) {
            router.replace("/setup");
            return;
          }
        }
      } catch {
        // If setup check fails, stay on login page
      }
    };
    checkSetup();
  }, [router]);

  useEffect(() => {
    if (state?.success && state.access_token) {
      localStorage.setItem("access_token", state.access_token);
      setToken(state.access_token);
      void fetchCurrentUser().then(() => router.replace("/dashboard"));
    }
  }, [state?.success, state?.access_token, router, setToken, fetchCurrentUser]);

  useEffect(() => {
    if (token) {
      router.replace("/dashboard");
    }
  }, [token, router]);

  return (
    <main className="flex min-h-screen items-center justify-center bg-gray-50 dark:bg-gray-900">
      <div className="w-full max-w-md space-y-6 rounded-lg bg-white dark:bg-gray-800 p-8 shadow-lg">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            {t("login.heading")}
          </h1>
          <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
            {t("login.subtitle")}
          </p>
        </div>

        {setupComplete && !state?.error && (
          <div
            role="status"
            className="rounded-md bg-green-100 p-4 text-sm text-green-800"
          >
            Setup complete! Sign in with the credentials you just created.
          </div>
        )}

        {state?.error && (
          <div
            role="alert"
            className="rounded-md bg-red-100 p-4 text-sm text-red-800"
          >
            {state.error}
          </div>
        )}

        <form action={formAction} className="space-y-5">
          <div>
            <label htmlFor="login-username" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
              {t("login.username")}
            </label>
            <input
              id="login-username"
              type="text"
              name="username"
              required
              disabled={isPending}
              className="mt-1 block w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-3 py-2 text-sm text-gray-900 dark:text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:opacity-70"
            />
          </div>
          <div>
            <label htmlFor="login-password" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
              {t("login.password")}
            </label>
            <input
              id="login-password"
              type="password"
              name="password"
              required
              disabled={isPending}
              className="mt-1 block w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-3 py-2 text-sm text-gray-900 dark:text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:opacity-70"
            />
          </div>
          <button
            type="submit"
            disabled={isPending}
            className="w-full rounded-md bg-blue-600 py-2 px-4 text-sm font-semibold text-white transition-colors hover:bg-blue-700 disabled:cursor-default disabled:opacity-70"
          >
            {isPending ? t("login.submitting") : t("login.submit")}
          </button>
        </form>
      </div>
    </main>
  );
}
