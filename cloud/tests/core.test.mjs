import test from "node:test";
import assert from "node:assert/strict";
import { createHandler, validateSnapshot, sha256Hex, MAX_BODY_BYTES, ALLOWED_ORIGIN } from "../functions/vortex-live/core.mjs";
import { createRestStore } from "../functions/vortex-live/store.mjs";

const NOW = Date.parse("2026-09-14T08:00:00.000Z");
const writer = "1".repeat(64), reader = "2".repeat(64);
const config = { ingestTokenSha256: await sha256Hex(writer), readerTokenSha256: await sha256Hex(reader), publicQuotes: false };
function fixture() {
  return {
    schemaVersion: 1, mode: "demo", sessionId: "21b4bc6a-4c71-4c62-a2a8-7f4036a139ed",
    sessionStartedAt: "2026-09-14T07:00:00.000Z", sequence: 10, producedAt: "2026-09-14T08:00:00.000Z",
    quote: { symbol: "XAUUSD", bid: 2500, ask: 2500.1, changedAtUtc: "2026-09-14T07:59:59Z" },
    status: { terminalConnected: true, algoTradingEnabled: false, eaRunning: false, demoVerified: true },
    account: { currency: "USD", balance: 50, equity: 50, freeMargin: 50, margin: 0 }, positions: [],
    strategy: { name: "VORTEX-XAU", version: "0.2.0", state: "waiting_for_baseline", reason: "not_activated", runnerMode: "observe" },
    signal: { decisionTimeServer: "2026-09-14T08:00:00", sessionUtcOffsetMinutes: null, ready: false, direction: 0, atr: null, consensus: null, scores: null },
  };
}
function req({ method = "GET", token = reader, body, origin, path = "/", headers = {} } = {}) {
  const h = { ...headers }; if (token !== null) h.authorization = `Bearer ${token}`;
  if (origin !== undefined) h.origin = origin;
  if (body !== undefined && !h["content-type"]) h["content-type"] = "application/json";
  return new Request(`https://example.test${path}`, { method, headers: h, ...(body !== undefined ? { body: typeof body === "string" ? body : JSON.stringify(body) } : {}) });
}
function setup(options = {}) {
  const calls = []; const row = { snapshot: fixture(), received_at: "2026-09-14T08:00:00+00:00" };
  const store = { async ingest(s) { calls.push(s); return { reason: "accepted", receivedAt: row.received_at }; }, async latest() { return row; }, ...options.store };
  return { row, calls, handle: createHandler({ config: { ...config, ...options.config }, store, now: () => options.now ?? NOW }) };
}

test("accepts $50 demo and preserves unknown broker timezone without inventing UTC", () => {
  const s = fixture(); s.quote.brokerTimeServer = "2026-09-14T11:00:00"; s.quote.brokerTimeBasis = "broker_server_unknown_offset";
  assert.deepEqual(validateSnapshot(s, { now: NOW }), s);
});
test("nested and top-level unknown fields never pass the whitelist", () => {
  for (const mutate of [s => s.password = "do-not-echo", s => s.account.login = 999, s => s.quote.credentials = "do-not-echo", s => s.strategy.accountId = 999, s => s.signal.extra = true]) {
    const s = fixture(); mutate(s);
    assert.throws(() => validateSnapshot(s, { now: NOW }), error => error.status === 422 && !error.message.includes("do-not-echo"));
  }
});
test("rejects real mode, unverifiable account data, invalid prices and unsafe numbers", () => {
  for (const mutate of [s => s.mode = "real", s => s.status.demoVerified = false, s => s.quote.ask = 2499, s => s.quote.bid = 0, s => s.account.margin = -1, s => s.account.balance = Infinity, s => s.sequence = Number.MAX_SAFE_INTEGER + 1]) {
    const s = fixture(); mutate(s); assert.throws(() => validateSnapshot(s, { now: NOW }));
  }
});
test("unverified terminal can publish only a redacted heartbeat", () => {
  const s = fixture(); s.status.demoVerified = false; s.account = null; s.quote = null;
  assert.equal(validateSnapshot(s, { now: NOW }).account, null);
  s.positions = [{ id: "3".repeat(64) }]; assert.throws(() => validateSnapshot(s, { now: NOW }));
});
test("requires exact UTC and fresh production, while weekend-old quotes remain distinguishable", () => {
  for (const produced of ["2026-09-14T08:00:00", "2026-09-14T08:00:00+00:00", "2026-02-30T08:00:00Z", "2026-09-14T08:00:31Z", "2026-09-14T07:57:59Z"]) {
    const s = fixture(); s.producedAt = produced; assert.throws(() => validateSnapshot(s, { now: NOW }));
  }
  const s = fixture(); s.quote.changedAtUtc = "2026-09-11T20:00:00Z";
  assert.equal(validateSnapshot(s, { now: NOW }).quote.changedAtUtc, s.quote.changedAtUtc);
});
test("ready signal cannot hide missing module scores; unready cannot direct an entry", () => {
  const s = fixture(); s.signal.ready = true; assert.throws(() => validateSnapshot(s, { now: NOW }));
  s.signal.ready = false; s.signal.direction = 1; assert.throws(() => validateSnapshot(s, { now: NOW }));
});
test("separate publisher and reader roles; unauthorized publisher cannot reach storage", async () => {
  const { handle, calls } = setup();
  assert.equal((await handle(req({ token: writer }))).status, 401);
  assert.equal((await handle(req({ method: "POST", body: fixture(), token: reader }))).status, 401);
  assert.equal(calls.length, 0);
  assert.equal((await handle(req({ method: "POST", body: fixture(), token: writer }))).status, 200);
  assert.equal(calls.length, 1);
  assert.equal((await handle(req())).status, 200);
});
test("rejects URL tokens, hostile origins, and unsupported preflight headers", async () => {
  const { handle } = setup();
  assert.equal((await handle(req({ path: `/?token=${reader}` }))).status, 400);
  assert.equal((await handle(req({ origin: "https://evil.test" }))).status, 403);
  assert.equal((await handle(req({ origin: "null" }))).status, 403);
  const valid = await handle(req({ method: "OPTIONS", token: null, origin: ALLOWED_ORIGIN, headers: { "access-control-request-method": "GET", "access-control-request-headers": "Authorization" } }));
  assert.equal(valid.status, 204); assert.equal(valid.headers.get("access-control-allow-origin"), ALLOWED_ORIGIN);
  const bad = await handle(req({ method: "OPTIONS", token: null, origin: ALLOWED_ORIGIN, headers: { "access-control-request-method": "GET", "access-control-request-headers": "X-Password" } }));
  assert.equal(bad.status, 403);
});
test("body cap is enforced even with absent or understated Content-Length", async () => {
  const { handle, calls } = setup();
  const large = " ".repeat(MAX_BODY_BYTES + 1);
  for (const headers of [{}, { "content-length": "2" }]) {
    assert.equal((await handle(req({ method: "POST", token: writer, body: large, headers }))).status, 413);
  }
  assert.equal(calls.length, 0);
});
test("rejects malformed JSON and compressed input", async () => {
  const { handle } = setup();
  assert.equal((await handle(req({ method: "POST", token: writer, body: "{" }))).status, 400);
  assert.equal((await handle(req({ method: "POST", token: writer, body: fixture(), headers: { "content-encoding": "gzip" } }))).status, 415);
});
test("private responses never cache; stale data is shown as stale rather than fresh or lost", async () => {
  const { handle } = setup({ now: NOW + 180000 }); const result = await handle(req({ origin: ALLOWED_ORIGIN }));
  assert.equal(result.status, 200); assert.match(result.headers.get("cache-control"), /no-store/);
  const data = await result.json(); assert.equal(data.state, "stale"); assert.equal(data.ageSeconds, 180); assert.equal(data.snapshot.account.balance, 50);
});
test("empty DB does not invent live market or account data", async () => {
  const { handle } = setup({ store: { latest: async () => null } });
  const data = await (await handle(req())).json(); assert.equal(data.state, "empty"); assert.equal(data.snapshot, null);
});
test("public quote route defaults off and exposes only its explicit quote projection", async () => {
  assert.equal((await setup().handle(req({ path: "/quotes", token: null }))).status, 404);
  const { handle } = setup({ config: { publicQuotes: true } });
  const result = await handle(req({ path: "/quotes", token: null })); assert.equal(result.status, 200);
  const data = await result.json(); assert.deepEqual(Object.keys(data).sort(), ["ageSeconds", "mode", "quote", "receivedAt", "schemaVersion", "state"]);
  assert.deepEqual(Object.keys(data.quote).sort(), ["ask", "bid", "changedAtUtc", "symbol"]);
  assert.equal((await handle(req({ token: null }))).status, 401);
});
test("retry/conflict result has correct HTTP semantics, upstream error details remain private", async () => {
  for (const [reason, expectedStatus] of [["duplicate", 200], ["not_newer", 409]]) {
    const { handle } = setup({ store: { ingest: async () => ({ reason, receivedAt: "2026-09-14T08:00:00Z" }) } });
    const result = await handle(req({ method: "POST", token: writer, body: fixture() }));
    assert.equal(result.status, expectedStatus); assert.equal((await result.json()).accepted, false);
  }
  const { handle } = setup({ store: { latest: async () => { throw Error("private-upstream-key"); } } });
  const result = await handle(req()); assert.equal(result.status, 503); assert.ok(!(await result.text()).includes("private-upstream-key"));
});
test("placeholder or identical role hashes fail closed", async () => {
  for (const change of [{ readerTokenSha256: "REPLACE" }, { readerTokenSha256: config.ingestTokenSha256 }]) {
    const { handle } = setup({ config: change }); assert.equal((await handle(req())).status, 503);
  }
});
test("REST adapter sends service credentials only to configured HTTPS origin and uses atomic RPC", async () => {
  const calls = [];
  const store = createRestStore({ url: "https://dedicated.example/rest/v1", serviceRoleKey: "synthetic-key", fetchImpl: async (url, options) => { calls.push([url, options]); return Response.json({ reason: "accepted" }); } });
  await store.ingest(fixture());
  assert.equal(calls[0][0], "https://dedicated.example/rest/v1/rpc/vortex_ingest_snapshot");
  assert.equal(calls[0][1].headers.apikey, "synthetic-key");
  assert.deepEqual(JSON.parse(calls[0][1].body), { p_snapshot: fixture() });
  assert.throws(() => createRestStore({ url: "http://external.example", serviceRoleKey: "synthetic-key" }));
  assert.throws(() => createRestStore({ url: "https://user:password@example.test" }));
});

function v02Fixture() {
  return {
    model: "VORTEX-XAU-EXTREME-v0.2", environment: "DEMO", mode: "FROZEN", action: "WAIT",
    metrics: Object.fromEntries(["balance", "equity", "floatingPnl", "realizedPnl", "dailyPnl", "dailyDrawdown", "maxDrawdown", "freeMargin", "usedMargin", "openRisk", "lockedProfit", "currentR"].map(k => [k, null])),
    context: { session: null, atr: null, volatilityState: null, nextNews: null },
    engines: Object.fromEntries(["orion", "vortex", "nova", "luna", "kira", "atlas"].map(k => [k, { score: null, status: "INVALID", reason: "baseline_not_passed" }])),
    consensus: null,
    protection: { confirmed: null, killSwitch: true, latencyMs: null, brokerConnected: false, dataFresh: false },
    journal: [{ time: "2026-09-14T08:00:00Z", event: "baseline_pending", reason: "No demo activation" }],
    position: null,
  };
}
test("v02 unavailable fields remain null, and the contract cannot relabel real money as demo", () => {
  const s = fixture(); s.v02 = v02Fixture();
  assert.deepEqual(validateSnapshot(s, { now: NOW }).v02, s.v02);
  s.v02.environment = "REAL"; assert.throws(() => validateSnapshot(s, { now: NOW }));
});
test("v02 rejects injected fields, incomplete engines, misleading percentages and unsafe text", () => {
  for (const mutate of [
    v => v.metrics.accountId = 999, v => delete v.engines.atlas,
    v => v.engines.kira.score = -1, v => v.engines.orion.status = "PASS",
    v => v.context.nextNews = "<script>alert(1)</script>", v => v.metrics.dailyDrawdown = 5,
    v => v.journal.push({ time: "2026-09-14T07:00:00Z", event: "older", reason: "out of order" }),
    v => v.journal = Array(51).fill(v.journal[0]),
  ]) {
    const s = fixture(); s.v02 = v02Fixture(); mutate(s.v02);
    assert.throws(() => validateSnapshot(s, { now: NOW }));
  }
});
test("v02 unverified heartbeat cannot carry account metrics or a position through optional data", () => {
  const s = fixture(); s.v02 = v02Fixture(); s.status.demoVerified = false; s.account = null; s.quote = null;
  assert.doesNotThrow(() => validateSnapshot(s, { now: NOW }));
  s.v02.metrics.balance = 50; assert.throws(() => validateSnapshot(s, { now: NOW }));
});
