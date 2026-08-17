import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export async function POST(req: NextRequest) {
  const refreshToken = req.cookies.get("refresh_token")?.value;
  if (!refreshToken) {
    return NextResponse.json({ error: "No refresh token" }, { status: 401 });
  }

  let apiRes: Response;
  try {
    apiRes = await fetch(`${API_BASE}/api/v1/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
      cache: "no-store",
    });
  } catch {
    return NextResponse.json({ error: "Server unreachable" }, { status: 502 });
  }

  const data = await apiRes.json().catch(() => ({}));

  if (!apiRes.ok) {
    const res = NextResponse.json(
      { error: data?.error?.message || "Token refresh failed" },
      { status: apiRes.status },
    );
    res.cookies.set("access_token", "", {
      httpOnly: true,
      sameSite: "strict",
      secure: process.env.NODE_ENV === "production",
      path: "/",
      maxAge: 0,
    });
    res.cookies.set("refresh_token", "", {
      httpOnly: true,
      sameSite: "strict",
      secure: process.env.NODE_ENV === "production",
      path: "/",
      maxAge: 0,
    });
    return res;
  }

  const res = NextResponse.json({ access_token: data.access_token });
  res.cookies.set("access_token", data.access_token, {
    httpOnly: true,
    sameSite: "strict",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 480 * 60,
  });
  return res;
}
