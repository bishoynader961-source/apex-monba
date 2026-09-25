import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const PROTECTED_ROUTES = [
  "/dashboard",
  "/pos",
  "/inventory",
  "/users",
  "/reports",
  "/settings",
  "/license",
  "/patients",
];

// Next.js 16 renamed the `middleware` file convention to `proxy` (the named
// export must be `proxy` too). Using `middleware.ts` / `export function
// middleware` emits a deprecation warning on every build and will be removed
// in a future minor. The `edge` runtime is not supported here — `proxy` always
// runs on the Node.js runtime, which is what this route logic wants anyway.
export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const accessToken = request.cookies.get("access_token")?.value;

  // ── Auth redirects ────────────────────────────────────────────────────────
  if (pathname === "/login" && accessToken) {
    return NextResponse.redirect(new URL("/dashboard", request.url));
  }

  if (pathname === "/" && !accessToken) {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  const isProtected = PROTECTED_ROUTES.some((route) =>
    pathname.startsWith(route)
  );
  if (isProtected && !accessToken) {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  // ── Currency header injection ─────────────────────────────────────────────
  // Forward a derived `x-local-currency` to route handlers / Server Components.
  // The supported API is `NextResponse.next({ request: { headers } })`: it
  // replaces the upstream request headers with the provided set (we seed it
  // from the incoming request, then add our header). Setting
  // `x-middleware-request-*` on the response by hand does NOT work — the
  // framework only consumes those when `x-middleware-override-headers` is also
  // present, which is an internal detail of this API.
  const country = request.headers.get("x-vercel-ip-country") ?? "US";
  const currency = country === "EG" ? "EGP" : "USD";

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-local-currency", currency);

  return NextResponse.next({ request: { headers: requestHeaders } });
}

export const config = {
  matcher: [
    // Page routes (API routes are skipped here to avoid overhead) …
    "/((?!api|_next/static|_next/image|favicon.ico).*)",
    // …except the one API route that must see the injected currency header.
    // Without this entry the `x-local-currency` header never reaches its only
    // reader (`app/api/currency/route.ts`) and it always falls back to USD.
    "/api/currency",
  ],
};
