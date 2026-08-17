import { NextRequest, NextResponse } from 'next/server';
import crypto from 'crypto';

/**
 * Paddle Billing webhook handler for Vercel/Next.js.
 *
 * Verifies HMAC-SHA256 signature using the ts=...;h1=... format.
 * On transaction.completed, proxies the event to the PythonAnywhere
 * license server which generates and stores the license in SQLite.
 */
export async function POST(req: NextRequest) {
  try {
    const signature = req.headers.get('paddle-signature') || '';
    const secret = process.env.PADDLE_WEBHOOK_SECRET;

    if (!secret) {
      console.error('[Paddle Webhook] PADDLE_WEBHOOK_SECRET not configured');
      return NextResponse.json({ error: 'Webhook not configured' }, { status: 500 });
    }

    // Parse Paddle-Signature header: "ts=TIMESTAMP;h1=HASH"
    const sigParts: Record<string, string> = {};
    for (const part of signature.split(';')) {
      const eqIdx = part.indexOf('=');
      if (eqIdx !== -1) {
        sigParts[part.substring(0, eqIdx)] = part.substring(eqIdx + 1);
      }
    }

    const ts = sigParts['ts'];
    const h1 = sigParts['h1'];

    if (!ts || !h1) {
      console.error('[Paddle Webhook] Missing ts or h1 in signature');
      return NextResponse.json({ error: 'Invalid signature format' }, { status: 401 });
    }

    // Verify HMAC-SHA256: signed payload is "{ts}:{rawBody}"
    const rawBody = await req.text();
    const signedPayload = `${ts}:${rawBody}`;
    const hmac = crypto.createHmac('sha256', secret);
    hmac.update(signedPayload);
    const computedHash = hmac.digest('hex');

    if (!crypto.timingSafeEqual(Buffer.from(computedHash, 'hex'), Buffer.from(h1, 'hex'))) {
      console.error('[Paddle Webhook] Signature mismatch');
      return NextResponse.json({ error: 'Invalid signature' }, { status: 401 });
    }

    const event = JSON.parse(rawBody);
    const eventType = event.event_type;

    // Proxy transaction.completed to the PythonAnywhere license server
    if (eventType === 'transaction.completed') {
      const serverUrl = process.env.NEXT_PUBLIC_API_URL || 'https://inventory1app1nn.pythonanywhere.com';

      try {
        const resp = await fetch(`${serverUrl}/api/webhook/paddle`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'paddle-signature': signature,
          },
          body: rawBody,
        });

        const result = await resp.json();
        console.log(`[Paddle Webhook] Proxied to ${serverUrl}: ${resp.status}`, result);
        return NextResponse.json(result, { status: resp.status });
      } catch (err) {
        console.error('[Paddle Webhook] Proxy failed:', err);
        return NextResponse.json({ error: 'Proxy failed' }, { status: 502 });
      }
    }

    // Acknowledge non-transaction events
    return NextResponse.json({ status: 'ok', event: eventType });
  } catch (error) {
    console.error('[Paddle Webhook] Processing error:', error);
    return NextResponse.json({ error: 'Internal Server Error' }, { status: 500 });
  }
}
