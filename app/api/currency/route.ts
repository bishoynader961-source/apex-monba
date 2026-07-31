import { NextResponse } from "next/server";

export async function GET(request: Request) {
  try {
    const currency = request.headers.get("x-local-currency");
    if (currency !== "USD" && currency !== "EGP") {
      return NextResponse.json({ currency: "USD" }, { status: 200 });
    }
    return NextResponse.json({ currency }, { status: 200 });
  } catch {
    return NextResponse.json({ currency: "USD" }, { status: 200 });
  }
}
