# Pharmacy Suite — Next.js frontend (B7)
# Build context: repository root. Uses the standalone output (next.config.ts).
FROM node:22-slim AS builder

WORKDIR /app

# Install dependencies first for better layer caching.
COPY package.json package-lock.json ./
RUN npm ci

# Build the standalone bundle (next build also type-checks the project).
# B7: pin the API base to the nginx edge. Next inlines NEXT_PUBLIC_* at build time,
# so the bundled frontend calls the proxy, not the unpublished :8000.
ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8080
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL}
COPY . .
RUN mkdir -p public && npm run build

# ── Runtime stage ──────────────────────────────────────────────────────────
FROM node:22-slim AS runner

WORKDIR /app
ENV NODE_ENV=production \
    PORT=3000

# Standalone server + required static/public assets.
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 3000
CMD ["node", "server.js"]
