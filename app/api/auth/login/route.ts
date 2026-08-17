import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import type { UserPublic } from "@/types/contracts";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => ({}));
  const { username, password } = body;

  if (!username || !password) {
    return NextResponse.json(
      { error: "Username and password are required" },
      { status: 400 },
    );
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
    return NextResponse.json({ error: "Server unreachable" }, { status: 502 });
  }

  const data = await apiRes.json().catch(() => ({}));

  if (!apiRes.ok) {
    const backendMsg =
      data?.error?.message ||
      (apiRes.status === 422 ? "Please check your input and try again" : "Invalid credentials");
    return NextResponse.json({ error: backendMsg }, { status: apiRes.status });
  }

  const res = NextResponse.json({
    success: true,
    user: data.user as UserPublic,
    access_token: data.access_token,
    refresh_token: data.refresh_token,
  });

  const accessMaxAge = 480 * 60;
  const refreshMaxAge = 30 * 24 * 60 * 60;
  const isProd = process.env.NODE_ENV === "production";

  res.cookies.set("access_token", data.access_token, {
    httpOnly: true,
    sameSite: "strict",
    secure: isProd,
    path: "/",
    maxAge: accessMaxAge,
  });
  res.cookies.set("refresh_token", data.refresh_token, {
    httpOnly: true,
    sameSite: "strict",
    secure: isProd,
    path: "/",
    maxAge: refreshMaxAge,
  });

  return res;
}
