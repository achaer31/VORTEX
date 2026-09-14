// Shared native Web API implementation: Deno Edge and local Node sidecar.
// This module handles telemetry only. It has no broker/order APIs.
export const MAX_BODY_BYTES = 128 * 1024;
export const ALLOWED_ORIGIN = "https://vortex-xau.vercel.app";
const HASH = /^[a-f0-9]{64}$/;
const UUID = /^[a-f0-9]{8}-[a-f0-9]{4}-[1-8][a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/i;
const SCORE_NAMES = ["orion", "vortex", "nova", "luna", "kira", "atlas"];
const encoder = new TextEncoder();

export class HttpError extends Error {
  constructor(status, code) { super(code); this.status = status; this.code = code; }
}
function invalid(path) { throw new HttpError(422, `invalid_${path}`); }
function object(value, required, optional, path) {
  if (!value || typeof value !== "object" || Array.isArray(value)) invalid(path);
  const allowed = new Set([...required, ...optional]);
  if (required.some(k => !Object.hasOwn(value, k)) || Object.keys(value).some(k => !allowed.has(k))) invalid(path);
}
function finite(value, min, max, path) {
  if (typeof value !== "number" || !Number.isFinite(value) || value < min || value > max) invalid(path);
}
function bool(value, path) { if (typeof value !== "boolean") invalid(path); }
function pattern(value, regex, path) { if (typeof value !== "string" || !regex.test(value)) invalid(path); }
function timestamp(value, path, utc = true) {
  pattern(value, utc ? /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?Z$/ : /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$/, path);
  const ms = Date.parse(utc ? value : `${value}Z`);
  if (!Number.isFinite(ms)) invalid(path);
  const normalized = utc ? value.replace(/Z$/, value.includes(".") ? "Z" : ".000Z") : `${value}.000Z`;
  if (new Date(ms).toISOString() !== normalized) invalid(path);
  return ms;
}
function positive(value, path) { finite(value, Number.MIN_VALUE, 1e9, path); }
function nullableNumber(value, min, max, path) { if (value !== null) finite(value, min, max, path); }
function safeText(value, max, path) {
  if (typeof value !== "string" || value.length < 1 || value.length > max || !/^[A-Za-z0-9 _.,:()/+\-]+$/.test(value)) invalid(path);
}

function validateV02(v, verified) {
  object(v, ["model", "environment", "mode", "action", "metrics", "context", "engines", "consensus", "protection", "journal"], ["position"], "v02");
  if (v.model !== "VORTEX-XAU-EXTREME-v0.2") invalid("v02_model");
  if (!["PAPER", "DEMO"].includes(v.environment)) invalid("v02_environment");
  if (!["NORMAL", "AGGRESSIVE", "EXTREME", "FROZEN", "KILL"].includes(v.mode)) invalid("v02_mode");
  if (!["LONG", "SHORT", "WAIT"].includes(v.action)) invalid("v02_action");
  const metrics = ["balance", "equity", "floatingPnl", "realizedPnl", "dailyPnl", "dailyDrawdown", "maxDrawdown", "freeMargin", "usedMargin", "openRisk", "lockedProfit", "currentR"];
  object(v.metrics, metrics, [], "v02_metrics");
  for (const key of metrics) {
    const drawdown = ["dailyDrawdown", "maxDrawdown"].includes(key);
    const nonnegative = drawdown || ["usedMargin", "openRisk", "lockedProfit"].includes(key);
    nullableNumber(v.metrics[key], nonnegative ? 0 : -1e12, drawdown ? 1 : 1e12, `v02_metrics_${key}`);
  }
  // No second channel for unverified broker account numbers.
  if (!verified && Object.values(v.metrics).some(x => x !== null)) invalid("v02_unverified_metrics");
  object(v.context, ["session", "atr", "volatilityState", "nextNews"], [], "v02_context");
  if (v.context.session !== null && !["ASIA", "LONDON", "NEWYORK", "LONDON_NEWYORK", "OTHER"].includes(v.context.session)) invalid("v02_session");
  if (v.context.atr !== null) positive(v.context.atr, "v02_atr");
  for (const k of ["volatilityState", "nextNews"]) if (v.context[k] !== null) safeText(v.context[k], k === "nextNews" ? 160 : 40, `v02_${k}`);
  object(v.engines, SCORE_NAMES, [], "v02_engines");
  for (const name of SCORE_NAMES) {
    const engine = v.engines[name];
    object(engine, ["score", "status", "reason"], [], "v02_engine");
    nullableNumber(engine.score, name === "kira" ? 0 : -100, 100, `v02_${name}_score`);
    if (!["PASS", "FAIL", "INVALID"].includes(engine.status)) invalid("v02_engine_status");
    if (engine.status !== "INVALID" && engine.score === null) invalid("v02_engine_score_missing");
    safeText(engine.reason, 160, "v02_engine_reason");
  }
  nullableNumber(v.consensus, -100, 100, "v02_consensus");
  object(v.protection, ["confirmed", "killSwitch", "latencyMs", "brokerConnected", "dataFresh"], [], "v02_protection");
  if (v.protection.confirmed !== null) bool(v.protection.confirmed, "v02_protection_confirmed");
  for (const k of ["killSwitch", "brokerConnected", "dataFresh"]) bool(v.protection[k], `v02_${k}`);
  nullableNumber(v.protection.latencyMs, 0, 3600000, "v02_latencyMs");
  if (!Array.isArray(v.journal) || v.journal.length > 50) invalid("v02_journal");
  let previous = -Infinity;
  for (const item of v.journal) {
    object(item, ["time", "event", "reason"], [], "v02_journal_item");
    const t = timestamp(item.time, "v02_journal_time");
    if (t < previous) invalid("v02_journal_order"); previous = t;
    safeText(item.event, 48, "v02_journal_event"); safeText(item.reason, 160, "v02_journal_reason");
  }
  if (Object.hasOwn(v, "position") && v.position !== null) {
    if (!verified) invalid("v02_unverified_position");
    object(v.position, ["averageEntry", "sl", "tp1", "tp2", "runnerLots", "pyramidCount"], [], "v02_position");
    for (const k of ["averageEntry", "sl", "tp1", "tp2"]) if (v.position[k] !== null) positive(v.position[k], `v02_position_${k}`);
    nullableNumber(v.position.runnerLots, 0, 200, "v02_runnerLots");
    if (!Number.isInteger(v.position.pyramidCount) || v.position.pyramidCount < 0 || v.position.pyramidCount > 3) invalid("v02_pyramidCount");
  }
}

export function validateSnapshot(s, { now = Date.now(), requireFresh = true } = {}) {
  object(s, ["schemaVersion", "mode", "sessionId", "sessionStartedAt", "sequence", "producedAt", "quote", "status", "account", "positions", "strategy"], ["signal", "v02"], "snapshot");
  if (s.schemaVersion !== 1 || s.mode !== "demo") invalid("demo_schema");
  pattern(s.sessionId, UUID, "sessionId");
  const started = timestamp(s.sessionStartedAt, "sessionStartedAt");
  const produced = timestamp(s.producedAt, "producedAt");
  if (!Number.isSafeInteger(s.sequence) || s.sequence < 0) invalid("sequence");
  if (produced < started) invalid("session_clock");
  if (requireFresh && (produced < now - 120000 || produced > now + 30000)) invalid("producedAt_freshness");

  object(s.status, ["terminalConnected", "algoTradingEnabled", "eaRunning", "demoVerified"], [], "status");
  for (const [k, v] of Object.entries(s.status)) bool(v, `status_${k}`);
  if (!Array.isArray(s.positions) || s.positions.length > 20) invalid("positions");
  if (!s.status.demoVerified && (s.account !== null || s.quote !== null || s.positions.length)) invalid("unverified_account_must_be_redacted");
  if (s.status.demoVerified && s.account === null) invalid("verified_account_missing");
  if (s.account !== null) {
    object(s.account, ["currency", "balance", "equity", "freeMargin", "margin"], [], "account");
    if (s.account.currency !== "USD") invalid("account_currency");
    for (const k of ["balance", "equity", "freeMargin"]) finite(s.account[k], -1e12, 1e12, `account_${k}`);
    finite(s.account.margin, 0, 1e12, "account_margin");
  }
  if (s.quote !== null) {
    object(s.quote, ["symbol", "bid", "ask", "changedAtUtc"], ["brokerTimeServer", "brokerTimeBasis"], "quote");
    if (s.quote.symbol !== "XAUUSD") invalid("quote_symbol");
    positive(s.quote.bid, "quote_bid"); positive(s.quote.ask, "quote_ask");
    if (s.quote.ask < s.quote.bid) invalid("quote_spread");
    if (timestamp(s.quote.changedAtUtc, "quote_changedAtUtc") > produced + 30000) invalid("quote_future");
    if (Object.hasOwn(s.quote, "brokerTimeServer") || Object.hasOwn(s.quote, "brokerTimeBasis")) {
      timestamp(s.quote.brokerTimeServer, "quote_brokerTimeServer", false);
      if (s.quote.brokerTimeBasis !== "broker_server_unknown_offset") invalid("quote_brokerTimeBasis");
    }
  }
  const ids = new Set();
  for (const p of s.positions) {
    object(p, ["id", "side", "lots", "openPrice", "currentPrice", "profit"], ["stopLoss", "takeProfit"], "position");
    pattern(p.id, HASH, "position_id");
    if (ids.has(p.id)) invalid("position_duplicate"); ids.add(p.id);
    if (!["buy", "sell"].includes(p.side)) invalid("position_side");
    finite(p.lots, Number.MIN_VALUE, 200, "position_lots");
    positive(p.openPrice, "position_openPrice"); positive(p.currentPrice, "position_currentPrice");
    finite(p.profit, -1e12, 1e12, "position_profit");
    for (const k of ["stopLoss", "takeProfit"]) if (Object.hasOwn(p, k) && p[k] !== null) positive(p[k], `position_${k}`);
  }
  object(s.strategy, ["name", "version", "state", "runnerMode"], ["reason"], "strategy");
  pattern(s.strategy.name, /^VORTEX(?:-[A-Z0-9]+)*$/, "strategy_name");
  if (s.strategy.name.length > 64) invalid("strategy_name");
  pattern(s.strategy.version, /^[A-Za-z0-9._-]{1,32}$/, "strategy_version");
  pattern(s.strategy.state, /^[a-z0-9_:-]{1,80}$/, "strategy_state");
  if (Object.hasOwn(s.strategy, "reason")) pattern(s.strategy.reason, /^[a-z0-9_:-]{1,80}$/, "strategy_reason");
  if (!["observe", "armed"].includes(s.strategy.runnerMode)) invalid("strategy_runnerMode");
  if (Object.hasOwn(s, "signal")) {
    object(s.signal, ["decisionTimeServer", "sessionUtcOffsetMinutes", "ready", "direction", "atr", "consensus", "scores"], [], "signal");
    const sig = s.signal;
    timestamp(sig.decisionTimeServer, "signal_decisionTimeServer", false);
    if (sig.sessionUtcOffsetMinutes !== null && (!Number.isInteger(sig.sessionUtcOffsetMinutes) || Math.abs(sig.sessionUtcOffsetMinutes) > 840)) invalid("signal_offset");
    bool(sig.ready, "signal_ready");
    if (![-1, 0, 1].includes(sig.direction) || (!sig.ready && sig.direction !== 0)) invalid("signal_direction");
    if (sig.atr !== null) positive(sig.atr, "signal_atr");
    if (sig.consensus !== null) finite(sig.consensus, -100, 100, "signal_consensus");
    if (sig.scores !== null) {
      object(sig.scores, SCORE_NAMES, [], "signal_scores");
      for (const k of SCORE_NAMES) if (sig.scores[k] !== null) finite(sig.scores[k], -100, 100, `signal_${k}`);
    }
    if (sig.ready && (sig.atr === null || sig.consensus === null || sig.scores === null || Object.values(sig.scores).some(v => v === null))) invalid("signal_ready_missing_values");
  }
  if (Object.hasOwn(s, "v02")) validateV02(s.v02, s.status.demoVerified);
  // Re-serialize the accepted whitelist, so callers cannot mutate shared references.
  return JSON.parse(JSON.stringify(s));
}

export async function sha256Hex(token) {
  const bytes = await crypto.subtle.digest("SHA-256", encoder.encode(token));
  return Array.from(new Uint8Array(bytes), b => b.toString(16).padStart(2, "0")).join("");
}
function sameHash(a, b) {
  let difference = 0;
  for (let i = 0; i < 64; i++) difference |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return difference === 0;
}
async function authorize(request, expected) {
  const match = /^Bearer ([a-f0-9]{64})$/.exec(request.headers.get("authorization") || "");
  if (!match || !sameHash(await sha256Hex(match[1]), expected)) throw new HttpError(401, "unauthorized");
}
export async function readJsonBody(request) {
  if (!/^application\/json(?:\s*;\s*charset=utf-8)?$/i.test(request.headers.get("content-type") || "")) throw new HttpError(415, "json_required");
  if (request.headers.has("content-encoding") && request.headers.get("content-encoding") !== "identity") throw new HttpError(415, "encoding_unsupported");
  const length = request.headers.get("content-length");
  if (length !== null && (!/^\d+$/.test(length) || Number(length) > MAX_BODY_BYTES)) throw new HttpError(413, "body_too_large");
  if (!request.body) throw new HttpError(400, "json_required");
  const reader = request.body.getReader(); const chunks = []; let size = 0;
  try {
    while (true) {
      const { value, done } = await reader.read(); if (done) break;
      size += value.byteLength;
      if (size > MAX_BODY_BYTES) { await reader.cancel(); throw new HttpError(413, "body_too_large"); }
      chunks.push(value);
    }
  } finally { reader.releaseLock(); }
  const bytes = new Uint8Array(size); let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
  try { return JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes)); }
  catch { throw new HttpError(400, "invalid_json"); }
}

function route(pathname) {
  if (["/", "/vortex-live", "/functions/v1/vortex-live", "/functions/v1/vortex-live/"].includes(pathname)) return "private";
  if (["/quotes", "/vortex-live/quotes", "/functions/v1/vortex-live/quotes"].includes(pathname)) return "quotes";
  return null;
}
export function createHandler({ config, store, now = () => Date.now() }) {
  const configured = config && HASH.test(config.ingestTokenSha256 || "") && HASH.test(config.readerTokenSha256 || "") && config.ingestTokenSha256 !== config.readerTokenSha256 && typeof config.publicQuotes === "boolean";
  return async function handle(request) {
    const origin = request.headers.get("origin");
    const headers = { "Cache-Control": "private, no-store", "Vary": "Origin", "X-Content-Type-Options": "nosniff", "Content-Type": "application/json; charset=utf-8" };
    if (origin === ALLOWED_ORIGIN) headers["Access-Control-Allow-Origin"] = origin;
    const response = (value, status = 200) => new Response(value === null ? null : JSON.stringify(value), { status, headers });
    try {
      if (origin && origin !== ALLOWED_ORIGIN) throw new HttpError(403, "origin_denied");
      const url = new URL(request.url); const target = route(url.pathname);
      if (url.search) throw new HttpError(400, "query_parameters_unsupported");
      if (!target || (target === "quotes" && !config?.publicQuotes)) throw new HttpError(404, "not_found");
      if (request.method === "OPTIONS") {
        if (origin !== ALLOWED_ORIGIN) throw new HttpError(403, "origin_denied");
        const method = request.headers.get("access-control-request-method");
        const allowed = target === "quotes" ? ["GET"] : ["GET", "POST"];
        const requestedHeaders = (request.headers.get("access-control-request-headers") || "").split(",").map(x => x.trim().toLowerCase()).filter(Boolean);
        if (!allowed.includes(method) || requestedHeaders.some(x => !["authorization", "content-type"].includes(x))) throw new HttpError(403, "preflight_denied");
        headers["Access-Control-Allow-Methods"] = allowed.join(", ");
        headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type";
        return response(null, 204);
      }
      if (!configured) throw new HttpError(503, "not_configured");
      if (request.method === "POST" && target === "private") {
        await authorize(request, config.ingestTokenSha256);
        const snapshot = validateSnapshot(await readJsonBody(request), { now: now() });
        const result = await store.ingest(snapshot);
        if (!result || !["accepted", "duplicate", "not_newer"].includes(result.reason)) throw new Error("store_result_invalid");
        return response({ accepted: result.reason === "accepted", reason: result.reason, receivedAt: result.receivedAt ?? null }, result.reason === "not_newer" ? 409 : 200);
      }
      if (request.method !== "GET") throw new HttpError(405, "method_not_allowed");
      if (target === "private") await authorize(request, config.readerTokenSha256);
      const row = await store.latest();
      if (!row) return response({ schemaVersion: 1, mode: "demo", state: "empty", receivedAt: null, ageSeconds: null, ...(target === "private" ? { snapshot: null } : { quote: null }) });
      const snapshot = validateSnapshot(row.snapshot, { now: now(), requireFresh: false });
      const receivedMs = Date.parse(row.received_at);
      if (!Number.isFinite(receivedMs)) throw new Error("stored_received_time_invalid");
      const ageSeconds = Math.max(0, Math.floor((now() - Date.parse(snapshot.producedAt)) / 1000));
      const receiveAgeSeconds = Math.max(0, Math.floor((now() - receivedMs) / 1000));
      const state = ageSeconds > 90 || receiveAgeSeconds > 90 ? "stale" : "fresh";
      const envelope = { schemaVersion: 1, mode: "demo", state, receivedAt: new Date(receivedMs).toISOString(), ageSeconds };
      if (target === "private") return response({ ...envelope, snapshot });
      // Never spread the stored snapshot or its account/status/strategy into a public response.
      const q = snapshot.quote;
      return response({ ...envelope, quote: q ? { symbol: q.symbol, bid: q.bid, ask: q.ask, changedAtUtc: q.changedAtUtc } : null });
    } catch (error) {
      if (error instanceof HttpError) return response({ error: error.code }, error.status);
      // Upstream failures may contain credentials or private data: do not log/echo them.
      return response({ error: "temporarily_unavailable" }, 503);
    }
  };
}
