import config from "./config.mjs";
import { createHandler } from "./core.mjs";
import { createRestStore } from "./store.mjs";

// Only the platform-provided service key is used; no broker keys belong here.
const url = Deno.env.get("SUPABASE_URL");
const serviceRoleKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
if (!url || !serviceRoleKey) throw new Error("platform_configuration_missing");
const store = createRestStore({ url: `${url.replace(/\/$/, "")}/rest/v1`, serviceRoleKey });
Deno.serve(createHandler({ config, store }));
