import { NextResponse } from "next/server";

export async function GET(request: Request) {
  const currency = request.headers.get("x-currency") || "USD";
  return NextResponse.json({ currency });
}
