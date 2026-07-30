import { NextResponse } from "next/server";
import crypto from "crypto";

function generateLicenseKey(email: string): string {
  const hash = crypto.createHash("sha256").update(email + Date.now()).digest("hex");
  return `PPRO-${hash.slice(0, 4).toUpperCase()}-${hash.slice(4, 8).toUpperCase()}-${hash.slice(8, 12).toUpperCase()}`;
}

function verifyPaddleSignature(body: string, signature: string, secret: string): boolean {
  const expected = crypto.createHmac("sha256", secret).update(body).digest("hex");
  return crypto.timingSafeEqual(Buffer.from(expected), Buffer.from(signature));
}

export async function POST(request: Request) {
  const body = await request.text();
  const signature = request.headers.get("paddle-signature") || "";
  const webhookSecret = process.env.PADDLE_WEBHOOK_SECRET || "";

  if (!verifyPaddleSignature(body, signature, webhookSecret)) {
    return NextResponse.json({ error: "Invalid signature" }, { status: 401 });
  }

  const event = JSON.parse(body);

  if (event.alert_name === "subscription_created") {
    const email = event.email;
    const licenseKey = generateLicenseKey(email);
    console.log("Paddle license created:", { email, licenseKey });
  }

  return NextResponse.json({ received: true });
}
