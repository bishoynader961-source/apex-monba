import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const PROTECTED_ROUTES = ["/dashboard", "/pos", "/inventory", "/users", "/reports", "/settings", "/license"];

export function middleware(request: NextRequest) {
  const country = request.headers.get("x-vercel-ip-country") || "US";
  const currency = country === "EG" ? "EGP" : "USD";

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-local-currency", currency);

  const { pathname } = request.nextUrl;
  const accessToken = request.cookies.get("access_token")?.value;

  if (pathname === "/login" && accessToken) {
    return NextResponse.redirect(new URL("/dashboard", request.url));
  }

  const isProtected = PROTECTED_ROUTES.some((route) => pathname.startsWith(route));
  if (isProtected && !accessToken) {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  return NextResponse.next({
    request: { headers: requestHeaders },
  });
}

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico).*)"],
};
