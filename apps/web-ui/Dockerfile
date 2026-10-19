# Build context: apps/web-ui.   docker build -t web-ui:1.0.0 apps/web-ui
# Build: Node (tag from docs/VERSIONS.md); run: nginx (stable line, D-44), as the unprivileged user 10001.
FROM node:24.21.0-slim AS build
WORKDIR /app
COPY package.json package-lock.json .npmrc ./
RUN npm ci --ignore-scripts
COPY . .
RUN npm run build

FROM nginx:1.30.5
COPY nginx/nginx.conf /etc/nginx/nginx.conf
COPY nginx/security-headers.conf /etc/nginx/security-headers.conf
# The base image's default pages (index.html, 50x.html) are not served.
RUN rm -rf /usr/share/nginx/html/*
COPY --from=build /app/dist /usr/share/nginx/html

# No configuration, secret or .env is part of the image: the page only knows two fixed local addresses (the CSP names the same).
USER 10001
EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=5 \
    CMD ["bash", "-c", "exec 3<>/dev/tcp/127.0.0.1/8080 && printf 'GET /health/liveness HTTP/1.0\\r\\n\\r\\n' >&3 && head -n1 <&3 | grep -q ' 200 '"]

# nginx runs in the foreground as PID 1; SIGTERM ends the workers gracefully (SIGQUIT would be even gentler, SIGTERM is fast enough
# for a static site).
CMD ["nginx", "-g", "daemon off;"]
