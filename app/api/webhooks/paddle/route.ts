import { NextRequest, NextResponse } from 'next/server';
import crypto from 'crypto';

// Helper to interact with Upstash Redis via REST, avoiding external package dependencies
async function setRedisKey(key: string, value: any) {
  const url = process.env.UPSTASH_REDIS_REST_URL;
  const token = process.env.UPSTASH_REDIS_REST_TOKEN;
  
  if (!url || !token) throw new Error("Upstash credentials missing");

  const response = await fetch(`${url}/set/${key}`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(value),
  });
  return response.json();
}

// Manually verify Paddle's HMAC-SHA256 webhook signature
function verifyPaddleSignature(signatureHeader: string, rawBody: string, secret: string) {
  const parts = signatureHeader.split(';');
  const tsPart = parts.find(p => p.startsWith('ts='));
  const h1Part = parts.find(p => p.startsWith('h1='));

  if (!tsPart || !h1Part) return false;

  const ts = tsPart.split('=')[1];
  const h1 = h1Part.split('=')[1];

  const payload = `${ts}:${rawBody}`;
  const hmac = crypto.createHmac('sha256', secret);
  hmac.update(payload);
  const computedSignature = hmac.digest('hex');

  return computedSignature === h1;
}

export async function POST(req: NextRequest) {
  try {
    const signature = req.headers.get('paddle-signature');
    const secret = process.env.PADDLE_WEBHOOK_SECRET;

    if (!signature || !secret) {
      return NextResponse.json({ error: 'Missing signature or secret' }, { status: 401 });
    }

    // Paddle signature verification requires the raw text body
    const rawBody = await req.text();
    const isValid = verifyPaddleSignature(signature, rawBody, secret);

    if (!isValid) {
      return NextResponse.json({ error: 'Invalid signature' }, { status: 401 });
    }

    const event = JSON.parse(rawBody);

    // Trigger license generation only on successful payments
    if (event.event_type === 'transaction.completed') {
      const customerEmail = event.data.customer?.email || 'unknown@email.com';
      const licenseKey = `PHARMA-${crypto.randomUUID().toUpperCase()}`;

      const licenseData = {
        email: customerEmail,
        status: 'active',
        created_at: new Date().toISOString(),
        device_bound: false // Ready for Python desktop client validation
      };

      // Save the license to Upstash Redis
      await setRedisKey(`license:${licenseKey}`, JSON.stringify(licenseData));
      console.log(`Successfully generated license for ${customerEmail}: ${licenseKey}`);
    }

    // Respond to Paddle quickly with a 200 OK
    return NextResponse.json({ status: 'ok' }, { status: 200 });
  } catch (error) {
    console.error('Webhook processing error:', error);
    return NextResponse.json({ error: 'Internal Server Error' }, { status: 500 });
  }
}
