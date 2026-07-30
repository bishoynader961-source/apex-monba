# Licensing System Deployment Guide

## File Structure

```
licensing/
├── api/
│   ├── index.py        # GET /api — Health check
│   ├── validate.py     # POST /api/validate — License + device binding
│   └── webhook.py      # POST /api/webhook — Lemon Squeezy order handler
├── static/
│   └── index.html      # Landing page (Tailwind CSS, dark theme)
├── main.py             # Desktop activation gate (ships with the app)
├── vercel.json         # Vercel routing config
├── requirements.txt    # Backend dependencies
├── DATABASE_DESIGN.md  # Upstash Redis schema
└── DEPLOY.md           # This file
```

---

## Step 1: Upstash Redis

1. Sign up at [upstash.com](https://upstash.com)
2. Create a new Redis database (region: closest to your users)
3. Copy the following from the dashboard:
   - `UPSTASH_REDIS_REST_URL`
   - `UPSTASH_REDIS_REST_TOKEN`

---

## Step 2: Lemon Squeezy

1. Sign up at [lemonsqueezy.com](https://lemonsqueezy.com)
2. Create a product: **PharmacyPro — Lifetime License** ($49)
3. Copy from Settings > API:
   - **Store ID**
   - **API Key** (private)
4. Set up a webhook:
   - **URL:** `https://your-project.vercel.app/api/webhook`
   - **Events:** `order_created`, `subscription_created`, `subscription_updated`
   - Copy the **Signing Secret**

---

## Step 3: Deploy to Vercel

### Option A: Vercel CLI

```bash
cd licensing/
npm i -g vercel
vercel login
vercel          # follow prompts, link to new project
vercel --prod   # deploy to production
```

### Option B: GitHub Integration

1. Push `licensing/` to a GitHub repo (or a subfolder of your existing repo)
2. Go to [vercel.com/new](https://vercel.com/new)
3. Import the repo
4. **Root Directory:** `licensing/` (if in a subfolder)
5. Framework Preset: **Other**
6. Deploy

### Set Environment Variables

In the Vercel dashboard, go to **Settings > Environment Variables** and add:

| Variable | Value |
|---|---|
| `UPSTASH_REDIS_REST_URL` | (from Step 1) |
| `UPSTASH_REDIS_REST_TOKEN` | (from Step 1) |
| `LEMONSQUEEZY_WEBHOOK_SECRET` | (from Step 2) |

---

## Step 4: Configure Lemon Squeezy Webhook

1. Go to Lemon Squeezy > Settings > Webhooks
2. Set the endpoint URL to your Vercel deployment:
   ```
   https://your-project.vercel.app/api/webhook
   ```
3. Select events: `order_created`, `subscription_created`
4. Copy the **Signing Secret** and add it to Vercel env vars as `LEMONSQUEEZY_WEBHOOK_SECRET`

---

## Step 5: Update Desktop Client

In `main.py` (the desktop launcher), replace the placeholder:

```python
API_BASE_URL = "https://your-project.vercel.app"
```

with your actual Vercel deployment URL.

---

## Step 6: Update Landing Page

In `static/index.html`, replace the checkout URL:

```html
<a href="https://your-store.lemonsqueezy.com/checkout" ...>
```

with your actual Lemon Squeezy checkout link.

---

## Step 7: Enable GitHub Pages (Optional)

If hosting the landing page via GitHub Pages instead of Vercel:

1. Push the `licensing/static/` folder to a `docs/` folder on the `main` branch
2. Go to repo Settings > Pages
3. Source: Deploy from branch > `main` > `/docs`
4. The landing page will be live at `https://your-username.github.io/repo-name/`

---

## Verification

1. **Health check:** `GET https://your-project.vercel.app/api` → `{"status":"ok"}`
2. **Validate (no key):** `POST /api/validate` with empty body → `{"valid":false}`
3. **Test webhook:** Place a test order in Lemon Squeezy (sandbox mode) → check Upstash Redis for the key
4. **Desktop activation:** Launch `main.py` → enter the license key from step 3 → app unlocks

---

## Key Format

```
PPRO-XXXX-XXXX-XXXX
```

- Prefix: `PPRO` (PharmacyPro)
- 3 groups of 4 alphanumeric characters
- Generated automatically by the webhook on successful order

---

## Troubleshooting

| Issue | Fix |
|---|---|
| `401 Invalid license key` | Key not in Redis. Check webhook fired and `order_created` was processed. |
| `403 Device limit exceeded` | Key bound to different hardware. Reset via Redis: `DEL license:<key>` |
| `500 Webhook error` | Check Vercel function logs. Verify `LEMONSQUEEZY_WEBHOOK_SECRET` matches. |
| Activation screen won't close | Check network. App requires one-time online validation on first launch. |
