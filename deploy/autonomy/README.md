# Autonomy evidence gate — NOT TESTED / NOT READY

This offline checker evaluates a reviewed **DEMO operational test**. It does not
shut down the Mac, disconnect a chat, contact MT5, send an order, change a Windows
task, call an LLM, publish telemetry, or send Telegram messages. The included
template has no acceptance evidence and returns `NOT_READY`. Current observer
preparation and passing software tests do not establish autonomous position
management or unattended restart.

The independent strategy baseline must also pass and receive a human review.
The current `NOT_EVALUABLE` strategy result cannot be overridden by claiming an
infrastructure test passed. Even a future `READY` result leaves
`baselineAutoGo`, `realTradingEnabled`, and `executionEnabledByEvaluator` false.
It is a report, not an execution permission or a promise of profitability.

## Run locally

Python 3.10+ standard library only. Keep actual evidence outside the checkout:

```console
python deploy/autonomy/evaluate.py /private/evidence/manifest.json --artifact-dir /private/evidence
python -m unittest discover -s deploy/autonomy/tests -v
```

Exit code 0 means all documented checks passed; exit code 2 means `NOT_READY`.
JSON is printed to stdout, containing check identifiers rather than private
artifact contents. The evaluator does not change files. Run the unchanged
template against an existing empty directory to observe its failing state.

Copy `evidence.template.json` into the private evidence directory. Populate it
only from an independently reviewed, supervised test. Do not change the template
to claim that testing happened, fabricate timestamps, relabel paper/synthetic
activity as DEMO, or disable a gate merely to get a green status.

## What counts as evidence

Every artifact reference is exactly `{ "path": "relative-file.json",
"sha256": "64 lowercase hex characters" }`. All referenced files must resolve
inside `--artifact-dir`. Absolute paths, `..`, Windows drive paths, symlink
escapes, digest mismatches, invalid JSON, duplicate JSON keys, and files larger
than 16 MiB fail closed. The raw `model` artifact is an exception to JSON parsing:
it is a copy of the exact deployed source/configuration bundle, without secrets.
Its digest must equal `model_sha256` throughout the evidence.

Use anonymized position hashes and a non-identifying operator alias. Never put
broker logins, account numbers, passwords, tokens, private keys, or Telegram IDs
in the package. Sensitive key names are rejected, but this is not a general
secret-redaction service: review original files before packaging them.

Checksums show that the files match the operator-reviewed versions. They do
**not** prove that a broker produced a log, that a machine was disconnected, or
that a person supervised a test. These artifacts are not digitally signed by a
broker. The operator must inspect the original DEMO terminal records, runtime
logs and host evidence and take responsibility for the attestation. Synthetic
unit fixtures mimic a complete schema to test the `READY` branch; they are not
acceptance proof and must never be reused as operational evidence.

## Manifest and attestation

For a completed review, `status` is `SUBMITTED`, `environment` is `DEMO`,
`origin` is `ACTUAL_DEMO`, and `model` is `VORTEX-XAU-EXTREME-v0.2`. `run_id`
is one non-identifying ASCII identifier, up to 64 letters/digits/underscores/dashes.
PAPER, REAL, SYNTHETIC and NOT_TESTED are not accepted as DEMO readiness.

The attestation requires all of:

- `alias`: non-identifying ASCII alias, up to 40 characters.
- `reviewed_at_utc`: real review time, in UTC with a `Z`, no older than 24 hours.
- `actual_demo_verified: true` and `not_synthetic: true`.
- `reviewed_artifact_sha256`: exact mapping of every artifact name to its digest.
- `statement`, exactly: `I reviewed the original DEMO evidence; these are actual observations, not synthetic fixtures or inferred success.`

Changing an artifact without reviewing and recording its new digest invalidates
the attestation. A successful run is a point-in-time assessment. It does not
guarantee future uptime or continue monitoring after the checker exits.

## Required artifact contracts

The manifest references **all ten** names below. Runtime evidence documents
(`runtime` through `blocking`) share `schemaVersion: 1`, `run_id`,
`environment: "DEMO"`, `origin: "ACTUAL_DEMO"`, and the same `model_sha256`.
Times use ISO UTC with `Z`. Missing fields fail closed.

| Artifact | Required contents and evaluation |
| --- | --- |
| `model` | Exact deployed deterministic source/configuration bundle, with secrets excluded. Raw SHA-256 equals manifest `model_sha256`. |
| `baseline_promotion` | Independent strategy report with `status: "ELIGIBLE_FOR_HUMAN_REVIEW"` and `reasons: []`. Copy the actual report, not a rewritten status. |
| `baseline_review` | `status: "PASSED_REVIEWED"`, matching `model_sha256` and `promotion_sha256`, `reviewer_approved: true`, plus the statistical evidence below. |
| `runtime` | `host: "WINDOWS_VPS"`, `process_kind: "DETERMINISTIC_DEMO_ENGINE"`, `execution_mode: "DEMO"`, `symbol: "XAUUSD"`, integer `runtime_llm_calls: 0`; `mac_dependency`, `chat_dependency`, `cloud_dependency`, `telegram_dependency` all false; matching `baseline_promotion_sha256`. These are operator-audited inventory statements, not facts inferred by this script. |
| `disconnect` | Supervised `begin_utc` / `end_utc` at least 15 minutes apart, ending within the past 24 hours and before the review. At least 31 ordered samples, with no gap over 30 seconds, spanning both ends of the window. Sample fields described below. |
| `ticks` | At least 30 actual `records` spanning the disconnect window without gaps over 30 seconds. Every record has `at_utc`, `broker_tick_utc`, positive finite `bid`/`ask` with ask ≥ bid, and `source: "BROKER_DEMO"`. Tick age at observation is 0..10 seconds. |
| `decisions` | At least three distinct, ordered decision records spanning at least ten minutes inside the disconnect window, with a consistent hash chain. The exact decision format is below. WAIT decisions count as engine activity, but cannot replace management evidence. |
| `recovery` | Exactly two `cases`: `CRASH_RECOVERY` and `UNATTENDED_BOOT`, linked to actual post-recovery management/reconciliation records. |
| `management` | Ordered, confirmed, unambiguous broker DEMO events showing entries, SL/TP confirmation and fills, winner-only pyramiding, kill and flat confirmation. Every entry needs reconciliation first. |
| `blocking` | Six supervised fault-injection cases in DEMO: REAL_ACCOUNT, AMBIGUOUS_ORDER, MISSING_STATE, STALE_DATA, UNCONFIRMED_PROTECTION, BASELINE_NOT_PASSED; every case must show zero order sends and link to an ENTRY_BLOCKED event. REAL_ACCOUNT is a DEMO test of the real-account rejection path, not a reason to trade on a real account. |

Baseline review also supplies `genuine_unseen`, `external_inputs_complete`, and
`broker_cost_history_verified`, all true; `campaigns >= 100`, `trading_days >= 60`,
`expectancy_ci95_low > 0`, `baseline_profit_factor > 1.2`,
`stress_profit_factor > 1`, `max_drawdown` in 0..0.15, `safety_failures: 0`, and
`positive_walkforward_fraction` between 2/3 and 1. The checker does not perform
new fitting or infer any of these values from software unit tests.

### Disconnect samples and decision records

Each disconnect sample has `at_utc`; false `mac_connected`, `chat_connected`,
`cloud_connected`, `telegram_connected`, `ambiguous_state`; true
`engine_running`, `broker_connected`, `data_fresh`; and integer
`runtime_llm_calls: 0`. Record actual dependency interruptions under supervision;
do not merely stop displaying the dashboard. Broker connectivity remains
available. Tick and decision evidence must continue during this same window.

Each decision record contains `recorded_utc`, `decision_utc`, `bar_open_utc`,
`source: "BROKER_DEMO"`, `model_sha256`, `action` (LONG/SHORT/WAIT), boolean
`ready`, `mode` (NORMAL/AGGRESSIVE/EXTREME/FROZEN/KILL), `previous_hash` and
`record_hash`. Decisions align to a UTC M5 close exactly five minutes after the
bar open. Unready, FROZEN or KILL decisions must say WAIT.
`recorded_utc` must be within 0..30 seconds after its decision timestamp and
inside the window. Additional non-sensitive decision facts may be included
in the hashed payload. Calculate `record_hash` as SHA-256 of UTF-8
JSON containing all fields except `record_hash`, with sorted keys and compact
separators `(',', ':')`. The first `previous_hash` is 64 zeroes; following
records reference the preceding digest. Preserve the original journal and its
provenance separately; this evidence-window chain is not an external timestamp
or a digital signature. Do not pass the observer journal directly without
documenting a lossless field mapping and reviewing it.

### Management and restart evidence

Every management event has unique `id`, `kind`, `at_utc`, `process_instance`,
`campaign`, `source: "BROKER_DEMO"`, `confirmed: true`, `ambiguous: false`.
Events are ascending, observed within the past 24 hours and before review.

`ENTRY_CONFIRMED` and `PYRAMID_ADDED` additionally require `position_hash`,
`symbol: "XAUUSD"`, positive `lots` and `price`. The same position hash cannot
be introduced twice. Before every entry, its process instance must already
have `ORDERS_RECONCILED`, `POSITIONS_RECONCILED` and `PROTECTION_CONFIRMED` events.
This includes the first entry after each recovery. Empty-account reconciliation
still needs an actual broker snapshot.

Within ten seconds of every entry there must be `SL_CONFIRMED` and
`TP_CONFIRMED` for that position hash, each with positive `price`. The package
must include actual `SL_FILLED` and `TP_FILLED` events tied to known positions,
with positive price and filled lots that do not exceed recorded entry volume.
It must also include at least one `PYRAMID_ADDED`, with positive
`floating_pnl_before` and true `winner_confirmed`, `all_prior_legs_protected`,
`risk_caps_passed`; no campaign may have more than two additions. These flags
must be supported by the original broker/runtime records reviewed by the
operator; the checker does not replace the independent risk engine.

For each `KILL_TRIGGERED`, a later same-campaign `FLAT_CONFIRMED` must show
integer `broker_positions_remaining: 0` and `broker_orders_remaining: 0`.
Unknown protection or an unresolved order cannot be declared confirmed.
No entry or pyramid may follow a kill during this acceptance run. A later
authorized reset needs a separately defined and reviewed test; this schema
does not silently infer rearming from a new date or process restart.

Each recovery case has `begin_utc`, `end_utc`, distinct `old_instance` and
`new_instance`, `started_without_interactive_login: true`, and `trigger` equal
to `ATSTARTUP` or `WINDOWS_SERVICE`. Its `event_ids` must link to reconciliation,
protection and a confirmed entry from that new process during the case window.
Both cases must be recent and reviewed. An ATLOGON task, reconnecting RDP, or
manually starting MT5 is **not unattended boot evidence**. The current Windows
observer task alone therefore cannot satisfy this gate.
The crash and boot cases must have distinct new process instances, nonoverlapping
time windows and disjoint referenced event IDs. One episode cannot prove both.

Each blocking case has `case`, `environment: "DEMO"`, `fault_injection: true`,
integer `order_send_count: 0`, and `event_id` linking to an `ENTRY_BLOCKED` event
whose `reason` equals the case name. Test these under supervision on DEMO;
evaluator code never injects a fault or changes a broker account.

## Verification scope

The synthetic tests exercise successful schema evaluation, missing/no activity,
baseline rejection, stale clocks and quotes, altered hash chains, dependency
loss, path traversal/symlink escape, unreconciled entries, protection and fill
coverage, ATLOGON rejection, unsafe order sends, and sensitive-field suppression.
They validate the checker only. No actual Mac-disconnect window, unattended VPS
boot, broker order, or position-management acceptance test was performed by
creating these files.
