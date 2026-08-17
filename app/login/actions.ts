"use server";

import { cookies } from "next/headers";
import type { UserPublic } from "@/types/contracts";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export interface LoginState {
  success?: boolean;
  error?: string;
  user?: UserPublic;
  access_token?: string;
  refresh_token?: string;
}

export async function loginAction(
  _prevState: LoginState | null,
  formData: FormData,
): Promise<LoginState> {
  const username = (formData.get("username") as string | null) ?? "";
  const password = (formData.get("password") as string | null) ?? "";

  if (!username || !password) {
    return { error: "Username and password are required" };
  }

  let apiRes: Response;
  try {
    apiRes = await fetch(`${API_BASE}/api/v1/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
      cache: "no-store",
    });
  } catch {
    return { error: "Server unreachable" };
  }

  const data = await apiRes.json().catch(() => ({}));

  if (!apiRes.ok) {
    const backendMsg =
      data?.error?.message ||
      (apiRes.status === 422 ? "Please check your input and try again" : undefined) ||
      "Invalid credentials";
    return { error: backendMsg };
  }

  const cookieStore = await cookies();
  const accessMaxAge = 480 * 60;
  const refreshMaxAge = 30 * 24 * 60 * 60;
  const isProd = process.env.NODE_ENV === "production";

  cookieStore.set("access_token", data.access_token, {
    httpOnly: true,
    sameSite: "strict",
    secure: isProd,
    path: "/",
    maxAge: accessMaxAge,
  });
  cookieStore.set("refresh_token", data.refresh_token, {
    httpOnly: true,
    sameSite: "strict",
    secure: isProd,
    path: "/",
    maxAge: refreshMaxAge,
  });

  return {
    success: true,
    user: data.user as UserPublic,
    access_token: data.access_token,
    refresh_token: data.refresh_token,
  };
}
