import { readFile, writeFile } from "node:fs/promises";
import { setTimeout } from "node:timers/promises";

const token = (await readFile("/run/secrets/reader_token", "utf8")).trim();
if (!/^[a-f0-9]{64}$/.test(token)) throw Error("reader_configuration_invalid");
let previous = null;
while (true) {
  let state = "unavailable";
  try {
    const response = await fetch("http://telemetry:8080/", { headers: { Authorization: `Bearer ${token}` }, signal: AbortSignal.timeout(8000) });
    if (response.ok) {
      const data = await response.json();
      if (["fresh", "stale", "empty"].includes(data.state)) state = data.state;
      if (state === "fresh" && !data.snapshot?.status?.demoVerified) state = "unverified";
      else if (state === "fresh" && !data.snapshot?.status?.terminalConnected) state = "terminal_disconnected";
    } else if (response.status === 401) state = "unauthorized";
  } catch { /* Network errors never include secrets or account data in logs. */ }
  if (state !== previous) {
    console.log(JSON.stringify({ component: "watchdog", time: new Date().toISOString(), state }));
    previous = state;
  }
  // Health of this process, independent of the terminal's online/offline condition.
  await writeFile("/tmp/watchdog-pulse", String(Date.now()), { mode: 0o600 });
  await setTimeout(30000);
}
