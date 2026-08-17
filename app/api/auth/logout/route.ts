import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

export async function POST(_req: NextRequest) {
  const res = NextResponse.json({ success: true });
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
