export function createRestStore({ url, serviceRoleKey = null, allowInternalHttp = false, fetchImpl = fetch }) {
  const base = new URL(url);
  if (base.username || base.password || base.search || base.hash || (base.protocol !== "https:" && !(allowInternalHttp && base.protocol === "http:" && base.hostname === "rest"))) throw new Error("invalid_store_url");
  const headers = { "Content-Type": "application/json" };
  if (serviceRoleKey) { headers.apikey = serviceRoleKey; headers.Authorization = `Bearer ${serviceRoleKey}`; }
  async function request(path, options = {}) {
    const response = await fetchImpl(`${base.href.replace(/\/$/, "")}/${path}`, { ...options, headers, redirect: "error", signal: AbortSignal.timeout(8000) });
    if (!response.ok) throw new Error("store_unavailable");
    return await response.json();
  }
  return {
    async ingest(snapshot) { return await request("rpc/vortex_ingest_snapshot", { method: "POST", body: JSON.stringify({ p_snapshot: snapshot }) }); },
    async latest() {
      const rows = await request("vortex_latest?select=snapshot,received_at&singleton=eq.true&limit=1");
      if (!Array.isArray(rows) || rows.length > 1) throw new Error("store_invalid");
      return rows[0] || null;
    },
  };
}
