# Operator supplies reviewed Node 24 image pinned with @sha256; no image is pulled by this template.
ARG NODE_IMAGE
FROM ${NODE_IMAGE}
WORKDIR /app
COPY functions ./functions
COPY local/server.mjs local/watchdog.mjs ./local/
USER node
EXPOSE 8080
CMD ["node", "local/server.mjs"]
