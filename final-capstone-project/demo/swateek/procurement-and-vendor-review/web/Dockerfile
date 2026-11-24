# Web image: Next.js standalone server. API_URL is read at request time by the /api proxy.
FROM node:22.23.4-alpine AS deps
WORKDIR /web
RUN corepack enable
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

FROM node:22.23.4-alpine AS build
WORKDIR /web
RUN corepack enable
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /web/node_modules ./node_modules
COPY . .
RUN pnpm build

FROM node:22.23.4-alpine
WORKDIR /web
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
COPY --from=build --chown=node /web/.next/standalone ./
COPY --from=build --chown=node /web/.next/static ./.next/static
COPY --from=build --chown=node /web/public ./public
USER node
EXPOSE 3000
CMD ["node", "server.js"]
