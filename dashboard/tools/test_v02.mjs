/* Synthetic browser-boundary tests. No real account, feed, token or market result.
 * The complete production v02.js executes inside a VM with a tiny inert DOM.
 * These checks cover safety semantics, not browser layout or strategy quality.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const production = fs.readFileSync(new URL('../v02.js', import.meta.url), 'utf8');
const NOW = Date.parse('2026-09-14T09:00:00.000Z');
const iso = offset => new Date(NOW + offset).toISOString();
const TOKEN = 'a'.repeat(64); // Deliberately synthetic, not a credential.

class InertNode {
  constructor(tag = 'div') {
    this.tag = tag; this.children = []; this.handlers = new Map();
    this.dataset = {}; this.value = ''; this.textContent = ''; this.hidden = false;
    this.classList = { toggle() {} }; this.style = { setProperty() {} };
  }
  get firstElementChild() {
    if (!this.children.length) this.children.push(new InertNode('span'));
    return this.children[0];
  }
  set innerHTML(_) { throw new Error('Raw HTML is forbidden in this synthetic DOM'); }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; }
  setAttribute(name, value) { this[name] = value; }
  addEventListener(name, callback) { this.handlers.set(name, callback); }
}

function harness() {
  const nodes = new Map(), created = [], requests = [], windowEvents = new Map();
  const node = id => { if (!nodes.has(id)) nodes.set(id, new InertNode()); return nodes.get(id); };
  const envButtons = ['BACKTEST', 'PAPER', 'DEMO'].map(env => {
    const element = new InertNode('button'); element.dataset.env = env; return element;
  });
  class FixedDate extends Date {
    constructor(...args) { super(...(args.length ? args : [NOW])); }
    static now() { return NOW; }
  }
  const sandbox = {
    Date: FixedDate, Number, Intl, Math, URL, AbortController,
    document: {
      getElementById: node,
      createElement(tag) { const element = new InertNode(tag); created.push(element); return element; },
      querySelectorAll(selector) { return selector === '[data-env]' ? envButtons : []; },
    },
    window: { addEventListener(name, callback) { windowEvents.set(name, callback); } },
    setTimeout() { return 1; }, clearTimeout() {}, setInterval() { return 1; }, clearInterval() {},
    fetch(url, options = {}) {
      requests.push({ url, options });
      return new Promise(() => {}); // Init stays pending; no I/O or real timers.
    },
    console: { log() { throw new Error('Unexpected logging'); }, error() { throw new Error('Unexpected logging'); } },
  };
  for (const key of ['localStorage', 'sessionStorage']) {
    Object.defineProperty(sandbox, key, { get() { throw new Error('Persistent browser storage forbidden'); } });
  }
  const context = vm.createContext(sandbox);
  vm.runInContext(production, context, { filename: 'dashboard/v02.js' });
  return {
    context, nodes, created, requests, node, windowEvents,
    run: code => vm.runInContext(code, context),
    set(value, environment = 'DEMO') {
      context.inputEnvelope = value;
      vm.runInContext(`environment=${JSON.stringify(environment)}; requestError=''; envelope=inputEnvelope;`, context);
    },
    click(id) { node(id).handlers.get('click')(); },
  };
}

function sample() {
  const engines = {};
  for (const key of ['orion', 'vortex', 'nova', 'luna', 'kira', 'atlas']) {
    engines[key] = { score: null, status: 'INVALID', reason: 'synthetic_input_unavailable' };
  }
  return {
    schemaVersion: 1, mode: 'demo', state: 'fresh', receivedAt: iso(0), ageSeconds: 0,
    snapshot: {
      schemaVersion: 1, mode: 'demo', sessionId: '00000000-0000-4000-8000-000000000001',
      sessionStartedAt: iso(-60000), sequence: 1, producedAt: iso(0),
      quote: { symbol: 'XAUUSD', bid: 4000, ask: 4000.2, changedAtUtc: iso(0) },
      status: { demoVerified: true, terminalConnected: true, algoTradingEnabled: false, eaRunning: true },
      account: { currency: 'USD', balance: 50, equity: 50, freeMargin: 50, margin: 0 },
      positions: [], strategy: { version: 'VORTEX-XAU-v0.1' },
      v02: {
        model: 'VORTEX-XAU-EXTREME-v0.2', environment: 'DEMO', mode: 'FROZEN', action: 'WAIT',
        metrics: { balance: 50, equity: 50 }, engines, journal: [], context: {}, consensus: null,
        protection: { dataFresh: true, brokerConnected: true, confirmed: null, killSwitch: false },
      },
    },
  };
}

test('PAPER and DEMO default disconnected without borrowing the backtest balance', () => {
  const h = harness();
  for (const env of ['PAPER', 'DEMO']) {
    h.run(`environment='${env}'`);
    assert.equal(h.run('liveState().valid'), false);
    assert.equal(h.run('liveView().metrics.balance'), undefined);
  }
});

test('fresh authenticated matching v0.2 snapshot is accepted only in its environment', () => {
  const h = harness(); h.set(sample());
  assert.equal(h.run('liveState().valid'), true);
  h.run("environment='PAPER'");
  assert.equal(h.run('liveState().valid'), false);
});

test('legacy DEMO quote cannot supply v0.2 engine scores or become PAPER v0.2', () => {
  const h = harness(), data = sample(); delete data.snapshot.v02; h.set(data);
  assert.equal(h.run('liveState().legacy'), true);
  assert.equal(h.run('Object.keys(liveView().engines).length'), 0);
  assert.equal(h.run('liveView().action'), 'WAIT');
  h.run("environment='PAPER'");
  assert.equal(h.run('liveState().valid'), false);
});

test('old or future quote/snapshot and cloud stale/empty states never look live', () => {
  const changes = [
    data => { data.snapshot.quote.changedAtUtc = iso(-10001); },
    data => { data.snapshot.quote.changedAtUtc = iso(2001); },
    data => { data.snapshot.producedAt = iso(-90001); },
    data => { data.snapshot.producedAt = iso(30001); },
    data => { data.ageSeconds = 91; },
    data => { data.state = 'stale'; },
    data => { data.state = 'empty'; data.snapshot = null; },
  ];
  for (const change of changes) {
    const h = harness(), data = sample(); change(data); h.set(data);
    assert.equal(h.run('liveState().valid'), false);
    assert.equal(h.run('liveView().metrics.balance'), undefined);
  }
});

test('unverified account, failed health, mismatched version and malformed quote are rejected', () => {
  const changes = [
    data => { data.snapshot.status.demoVerified = false; },
    data => { data.snapshot.status.terminalConnected = false; },
    data => { data.snapshot.account.currency = 'EUR'; },
    data => { data.snapshot.quote.symbol = 'EURUSD'; },
    data => { data.snapshot.quote.ask = 3999; },
    data => { data.snapshot.quote.bid = null; },
    data => { data.snapshot.v02.model = 'legacy'; },
    data => { data.snapshot.v02.protection.dataFresh = false; },
    data => { data.snapshot.v02.mode = 'UNCONTROLLED'; },
  ];
  for (const change of changes) {
    const h = harness(), data = sample(); change(data); h.set(data);
    assert.equal(h.run('liveState().valid'), false);
  }
});

test('unsafe endpoint or malformed token never issues an authenticated request', () => {
  const cases = [
    ['http://example.test/feed', TOKEN], ['https://user:pass@example.test/feed', TOKEN],
    ['https://example.test/feed?token=secret', TOKEN], ['https://example.test/feed#secret', TOKEN],
    ['javascript:alert(1)', TOKEN], ['https://example.test/feed', 'bad-token'],
    ['https://example.test/feed', 'g'.repeat(64)],
    ['https://example.test/feed', 'A'.repeat(64)],
  ];
  for (const [url, token] of cases) {
    const h = harness(); h.node('endpoint').value = url; h.node('reader-token').value = token;
    h.click('connect-button');
    assert.equal(h.requests.filter(r => r.options.headers?.Authorization).length, 0);
    assert.equal(h.run('reader'), '');
  }
});

test('valid token goes only into Authorization; clear removes it from memory and field', () => {
  const h = harness();
  h.node('endpoint').value = 'https://example.test/feed'; h.node('reader-token').value = TOKEN;
  h.click('connect-button');
  const request = h.requests.find(r => r.options.headers?.Authorization);
  assert.ok(request);
  assert.equal(request.url, 'https://example.test/feed');
  assert.equal(request.options.headers.Authorization, 'Bearer ' + TOKEN);
  assert.equal(request.options.credentials, 'omit');
  assert.equal(request.options.referrerPolicy, 'no-referrer');
  assert.equal(request.options.redirect, 'error');
  assert.equal(request.options.cache, 'no-store');
  assert.equal(h.node('reader-token').value, '');
  h.click('disconnect-button');
  assert.equal(h.run('reader'), ''); assert.equal(h.run('endpoint'), '');
  assert.equal(request.options.signal.aborted, true);
});

test('network failure clears the old snapshot and renders unavailable account metrics', async () => {
  const h = harness(); h.set(sample());
  h.context.fetch = async () => ({ ok: false, status: 503 });
  await h.run(`endpoint='https://example.test/feed';reader='${TOKEN}';poll()`);
  assert.equal(h.run('envelope'), null);
  assert.equal(h.run('liveState().valid'), false);
  assert.equal(h.node('m-balance').textContent, '—');
});

test('response from an aborted earlier connection cannot overwrite a newer connection', async () => {
  const h = harness(); let resolveOld;
  h.context.fetch = () => new Promise(resolve => { resolveOld = resolve; });
  const oldPoll = h.run(`endpoint='https://example.test/old';reader='${TOKEN}';poll()`);
  h.run('disconnect()');
  const fresh = sample(); fresh.snapshot.sequence = 2;
  h.context.fetch = async () => ({ ok: true, json: async () => fresh });
  await h.run(`endpoint='https://example.test/new';reader='${TOKEN}';poll()`);
  const old = sample(); old.snapshot.sequence = 1;
  resolveOld({ ok: true, json: async () => old }); await oldPoll;
  assert.equal(h.run('envelope.snapshot.sequence'), 2);
});

test('external reason text remains literal and never enters an HTML sink', () => {
  const h = harness(), data = sample();
  data.snapshot.v02.engines.atlas.reason = '<img src=x onerror=alert(1)>';
  data.snapshot.v02.journal = [{ time: iso(0), event: '<script>', reason: '<iframe src=evil>' }];
  h.set(data); h.run('render()');
  assert.ok(h.created.some(node => node.textContent === '<img src=x onerror=alert(1)>'));
  assert.ok(!h.created.some(node => node.tag === 'img' || node.tag === 'script' || node.tag === 'iframe'));
});

test('page hide disposes the private connection rather than persisting it', () => {
  const h = harness();
  h.run(`reader='${TOKEN}';endpoint='https://example.test/feed'`);
  h.windowEvents.get('pagehide')();
  assert.equal(h.run('reader'), ''); assert.equal(h.run('envelope'), null);
});

test('a substituted backtest report with another model stays unavailable', async () => {
  const h = harness();
  h.context.fetch = async () => ({ ok: true, json: async () => ({
    schemaVersion: 2, environment: 'BACKTEST', liveFeed: false,
    model: 'UNRELATED-MODEL', scenarios: [{ id: 'synthetic' }],
  }) });
  await h.run('init()');
  assert.equal(h.run('report'), null);
  assert.equal(h.node('m-balance').textContent, '—');
});

test('observer lock does not claim that broker liquidation is active', () => {
  const h = harness(), data = sample();
  data.snapshot.strategy.runnerMode = 'observe';
  data.snapshot.v02.protection.killSwitch = true;
  h.set(data); h.run('render()');
  assert.ok(h.created.some(node => node.textContent === 'ENTRY TERKUNCI / OBSERVER'));
  assert.ok(h.created.some(node => node.textContent === 'Tidak ada posisi XAUUSD pada snapshot ini.'));
});
