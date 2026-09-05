# StackSense frontend — Next.js 16 / React 19.
#
# NEXT_PUBLIC_* variables are inlined into the client JS bundle at BUILD time,
# not read at container start. Since this app calls the API directly from the
# browser (not through a Next.js server-side proxy), the URL baked in here
# must be one the *user's browser* can resolve — not a Docker-internal
# hostname like "api", which only exists inside the compose network.
# http://localhost:8000 works because Docker Desktop on Windows publishes the
# api container's port 8000 onto the host's localhost.

# ---------- deps ----------
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# ---------- build ----------
FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

RUN npm run build

# ---------- runtime ----------
FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production

COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

EXPOSE 3000
CMD ["node", "server.js"]
