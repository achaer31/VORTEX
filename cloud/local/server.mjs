import { createServer } from "node:http";
import { Readable } from "node:stream";
import { pathToFileURL } from "node:url";
import { createHandler } from "../functions/vortex-live/core.mjs";
import { createRestStore } from "../functions/vortex-live/store.mjs";

const { default: config } = await import(pathToFileURL(process.env.VORTEX_CONFIG_FILE || "/run/secrets/config.mjs").href);
const store = createRestStore({ url: "http://rest:3000", allowInternalHttp: true });
const handle = createHandler({ config, store });
const server = createServer({ maxHeaderSize: 16384 }, async (incoming, outgoing) => {
  try {
    if (incoming.url === "/healthz" && incoming.method === "GET") {
      outgoing.writeHead(200, { "Content-Type": "application/json", "Cache-Control": "no-store" });
      outgoing.end('{"status":"process_running"}'); return;
    }
    const method = incoming.method || "GET";
    const request = new Request(`http://telemetry:8080${incoming.url}`, {
      method, headers: incoming.headers,
      ...(["GET", "HEAD"].includes(method) ? {} : { body: Readable.toWeb(incoming), duplex: "half" }),
    });
    const response = await handle(request);
    outgoing.writeHead(response.status, Object.fromEntries(response.headers));
    outgoing.end(Buffer.from(await response.arrayBuffer()));
  } catch {
    outgoing.writeHead(503, { "Content-Type": "application/json", "Cache-Control": "no-store" });
    outgoing.end('{"error":"temporarily_unavailable"}');
  }
});
server.requestTimeout = 15000;
server.headersTimeout = 10000;
server.keepAliveTimeout = 5000;
server.setTimeout(15000);
server.listen(8080, "0.0.0.0");
for (const sig of ["SIGTERM", "SIGINT"]) process.on(sig, () => server.close(() => process.exit(0)));
