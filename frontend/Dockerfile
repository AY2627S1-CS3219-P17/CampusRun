# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-09-27
# Scope: AI-generated two-stage Dockerfile: builds the Vite app with Node, then serves the static files with nginx.
# Author review: <to be completed by author>

# ---- Build: compile the app into static files in /app/dist ----
# Matches the Node version pinned in mise.toml
FROM node:24.18.0-alpine AS build

WORKDIR /app

# Install dependencies only, so this layer stays cached until the lockfile changes
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci

COPY . .
RUN npm run build

# ---- Serve: only the built files, no Node or source code ----
FROM nginx:stable-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
