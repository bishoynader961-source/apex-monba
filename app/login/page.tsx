"use client";

import { useRouter } from "next/navigation";
import { useActionState, useEffect } from "react";

import { loginAction } from "@/app/login/actions";
import { useAuthStore } from "@/stores/authStore";

export default function LoginPage() {
  const router = useRouter();
  const [state, formAction, isPending] = useActionState(loginAction, null);
  const setToken = useAuthStore((s) => s.setToken);
  const fetchCurrentUser = useAuthStore((s) => s.fetchCurrentUser);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);

  useEffect(() => {
    if (state?.success && state.access_token) {
      localStorage.setItem("access_token", state.access_token);
      setToken(state.access_token);
      void fetchCurrentUser().then(() => router.replace("/dashboard"));
    }
  }, [state?.success, state?.access_token, router, setToken, fetchCurrentUser]);

  if (isAuthenticated()) {
    router.replace("/dashboard");
    return null;
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-gray-50 dark:bg-gray-900">
      <div className="w-full max-w-md space-y-6 rounded-lg bg-white dark:bg-gray-800 p-8 shadow-lg">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            Pharmacy Suite — Sign In
          </h1>
          <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
            Enter your credentials to continue.
          </p>
        </div>

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
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
              Username
            </label>
            <input
              type="text"
              name="username"
              required
              disabled={isPending}
              className="mt-1 block w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-3 py-2 text-sm text-gray-900 dark:text-gray-100 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:opacity-70"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
              Password
            </label>
            <input
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
            {isPending ? "Signing in…" : "Sign In"}
          </button>
        </form>
      </div>
    </main>
  );
}
