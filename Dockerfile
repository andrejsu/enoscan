FROM node:22.22.2-bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git openssh-client postgresql-client python3 ripgrep gosu \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace/Vinolog
COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/package.json
RUN npm ci

COPY . .
RUN npm run prepare:nuxt && npm run check

RUN mkdir -p /home/node/.codex \
    && chown -R node:node /workspace/Vinolog /home/node/.codex
COPY scripts/dev-entrypoint.sh /usr/local/bin/dev-entrypoint
COPY scripts/dev-shell.sh /usr/local/bin/sh
RUN chmod +x /usr/local/bin/dev-entrypoint /usr/local/bin/sh
ENV HOME=/workspace/Vinolog/.docker-home
ENV CODEX_HOME=/home/node/.codex
ENV HOST=0.0.0.0
ENV PORT=3000
EXPOSE 3000
ENTRYPOINT ["/usr/local/bin/dev-entrypoint"]
CMD ["npm", "run", "dev"]
