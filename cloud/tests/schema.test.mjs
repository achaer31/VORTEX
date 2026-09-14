import test, { before, after } from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

// An optional local path supports constrained environments without installing globally.
const { PGlite } = await import(process.env.PGLITE_MODULE || "@electric-sql/pglite");
let db;
before(async () => {
  db = new PGlite();
  await db.exec("create role anon; create role authenticated; create role service_role bypassrls;");
  await db.exec(await readFile(new URL("../schema.sql", import.meta.url), "utf8"));
});
after(async () => { await db?.close(); });
const iso = value => new Date(value).toISOString();
function snapshot(overrides = {}) {
  const t = Date.now() - 10000;
  return { schemaVersion: 1, mode: "demo", sessionId: "21b4bc6a-4c71-4c62-a2a8-7f4036a139ed", sessionStartedAt: iso(t - 60000), sequence: 1, producedAt: iso(t), ...overrides };
}
async function ingest(s) {
  return (await db.query("select public.vortex_ingest_snapshot($1::jsonb) as result", [JSON.stringify(s)])).rows[0].result;
}
async function asRole(role, action) {
  await db.exec(`set role ${role}`);
  try { return await action(); } finally { await db.exec("reset role"); }
}
test("database table and RPC deny anon/authenticated; service_role has explicit access", async () => {
  for (const role of ["anon", "authenticated"]) {
    await asRole(role, async () => {
      await assert.rejects(() => db.query("select * from public.vortex_latest"), /permission denied/);
      await assert.rejects(() => ingest(snapshot()), /permission denied/);
    });
  }
  const flags = (await db.query("select relrowsecurity, relforcerowsecurity from pg_class where oid='public.vortex_latest'::regclass")).rows[0];
  assert.deepEqual(flags, { relrowsecurity: true, relforcerowsecurity: true });
  assert.equal((await db.query("select count(*)::int as n from pg_policies where tablename='vortex_latest'")).rows[0].n, 0);
  await asRole("service_role", async () => assert.deepEqual((await db.query("select * from public.vortex_latest")).rows, []));
});
test("atomic latest row rejects reordered delivery, accepts a new session, retires the old session", async () => {
  await asRole("service_role", async () => {
    const s = snapshot();
    const first = await ingest(s); assert.equal(first.reason, "accepted");
    const retry = await ingest(s); assert.equal(retry.reason, "duplicate"); assert.equal(retry.receivedAt, first.receivedAt);
    assert.equal((await ingest({ ...s, sequence: 0 })).reason, "not_newer");
    assert.equal((await ingest({ ...s, sequence: 2, producedAt: iso(Date.parse(s.producedAt) - 1) })).reason, "not_newer");
    const second = { ...s, sequence: 2, producedAt: iso(Date.parse(s.producedAt) + 1) };
    assert.equal((await ingest(second)).reason, "accepted");
    const restart = { ...second, sessionId: "ba47b71b-98a1-44a2-9536-42d5e5d5e95c", sessionStartedAt: iso(Date.parse(second.producedAt) + 1), producedAt: iso(Date.parse(second.producedAt) + 2), sequence: 0 };
    assert.equal((await ingest(restart)).reason, "accepted");
    assert.equal((await ingest({ ...second, sequence: 999, producedAt: iso(Date.parse(restart.producedAt) + 10) })).reason, "not_newer");
    assert.equal((await ingest({ ...restart, sessionStartedAt: iso(Date.parse(restart.sessionStartedAt) + 1), sequence: 1 })).reason, "not_newer");
    const rows = (await db.query("select * from public.vortex_latest")).rows;
    assert.equal(rows.length, 1); assert.equal(rows[0].session_id, restart.sessionId); assert.equal(rows[0].sequence, 0);
  });
});
test("database boundary also rejects real mode, unsafe sequence, and invalid clock values", async () => {
  await asRole("service_role", async () => {
    for (const overrides of [{ mode: "real" }, { sequence: -1 }, { sequence: 9007199254740992 }, { producedAt: iso(Date.now() - 121000), sessionStartedAt: iso(Date.now() - 130000) }, { producedAt: iso(Date.now() + 31000) }, { producedAt: "infinity" }]) {
      await assert.rejects(() => ingest(snapshot(overrides)));
    }
  });
});
