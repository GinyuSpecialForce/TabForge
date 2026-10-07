# syntax=docker/dockerfile:1
# TabForge web app. Build context is the web/ directory:
#   docker build ./web

# --- Build stage: install deps and compile the Next.js app ----------------
FROM node:22-alpine AS build
WORKDIR /app

COPY package.json package-lock.json ./
# npm cache mount: lockfile changes re-install from disk instead of the network.
RUN --mount=type=cache,target=/root/.npm \
    npm ci --no-audit --no-fund

COPY . .

# .next/cache mount: Next.js's incremental build cache survives rebuilds, so
# source edits rebuild incrementally instead of from scratch.
RUN --mount=type=cache,target=/app/.next/cache \
    npm run build

# --- Runtime stage: traced standalone server only -------------------------
# output:"standalone" ships just the node_modules files Next.js traces, so the
# final image skips the dev node_modules (~356MB) and the source tree -- image
# export/unpack time drops proportionally.
FROM node:22-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production \
    HOSTNAME=0.0.0.0 \
    PORT=3000

# The standalone server serves public/ itself.
COPY --from=build /app/public ./public
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static

EXPOSE 3000
CMD ["node", "server.js"]
