# syntax=docker/dockerfile:1

# Decalove web client — build once, configure where it runs.
#
# The bundle is static, so the API address cannot be compiled into it without needing
# one image per environment. It is written to /config.js from the container's own
# environment at start-up instead (see docker-entrypoint.d below).

FROM node:24-alpine AS build
WORKDIR /build

# Dependencies first, so a source-only change does not reinstall them.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
# No VITE_* here on purpose: baking an API address in is exactly what the runtime
# config exists to avoid. The build-time fallback stays at its localhost default and
# is never what a container uses.
RUN npm run build


FROM nginx:1.29-alpine AS runtime

# nginx:alpine renders /etc/nginx/templates/*.template with envsubst and runs every
# executable in /docker-entrypoint.d/ before starting. Both mechanisms are the image's
# own; nothing here overrides the entrypoint.
COPY --from=build /build/dist /usr/share/nginx/html
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY docker-entrypoint.d/ /docker-entrypoint.d/
RUN sed -i 's/\r$//' /etc/nginx/templates/default.conf.template /docker-entrypoint.d/*.sh \
    && chmod +x /docker-entrypoint.d/*.sh

# DECALOVE_API_BASE — where the *browser* sends API calls.
#   Empty (the default) means same-origin: calls go to /api/ on this server and nginx
#   proxies them onward, which removes CORS and the http/https mismatch in one move.
#   Set an absolute URL to have the browser reach the API directly; the proxy is then
#   simply unused.
# DECALOVE_API_UPSTREAM — where *this server* forwards /api/. A service name on the
#   compose network, or any address this container can reach.
ENV DECALOVE_API_BASE=""
ENV DECALOVE_API_PREFIX="/api/v1"
ENV DECALOVE_API_UPSTREAM="http://api:8000"
ENV DECALOVE_PORT="80"

EXPOSE 80

HEALTHCHECK --interval=15s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -q -O /dev/null "http://127.0.0.1:${DECALOVE_PORT}/config.js" || exit 1
