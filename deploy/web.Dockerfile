FROM node:22.22.2-bookworm-slim AS build

WORKDIR /src
COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/package.json
RUN npm ci

COPY tsconfig.json ./
COPY apps/web apps/web
RUN npm run prepare:nuxt && npm run build

FROM node:22.22.2-bookworm-slim

ENV NODE_ENV=production
ENV HOST=0.0.0.0
ENV PORT=3000

WORKDIR /app
COPY --from=build --chown=node:node /src/apps/web/.output ./.output

USER node
EXPOSE 3000
HEALTHCHECK --interval=10s --timeout=3s --retries=30 \
  CMD node -e "fetch('http://127.0.0.1:3000/').then(r => process.exit(r.ok ? 0 : 1)).catch(() => process.exit(1))"
CMD ["node", ".output/server/index.mjs"]
