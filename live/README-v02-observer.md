# v0.2 read-only observer and private delivery

Prepared locally; **not installed, connected, or activated on the VPS**. The current NO-GO result is unchanged. No code here makes a baseline pass, gives permission to use real funds, or enables execution.

`observe_v02.py` is a standalone terminal reader with no transaction/authentication API calls. It does not import the legacy execution module. Its default invocation and `--check` only validate Python imports and private configuration; they do not import MetaTrader5, initialize the terminal, create state, read the account, or start a worker. Explicit `--observe` additionally requires `VORTEX_BASELINE_STATUS=passed_reviewed` and Windows. This environment flag is a manual operator gate, not cryptographic proof of review; **do not set it to bypass the actual baseline**.

The terminal must already be signed into the expected demo account. Every snapshot checks expected identity, DEMO mode, USD currency, hedging mode, connectivity and finite account values, then checks again before writing. Failed verification produces a redacted heartbeat without account, quote, positions or v0.2 financial metrics. The code never prints identity values. `algoTradingEnabled` reports terminal state; `eaRunning:false` truthfully states that this reader is not an EA.

## Private configuration

Keep all runtime settings and files outside the repository. Required existing variables are `VORTEX_EXPECTED_LOGIN`, `VORTEX_SESSION_UTC_OFFSET_MINUTES=0`, and `VORTEX_STATE_DIR`. The offset is explicit: this v0.2 model only supports the verified Exness GMT+0 setup, while the MT5 Python API supplies UTC timestamps. An optional `VORTEX_TERMINAL_PATH` selects the installed terminal. No broker password is accepted by this reader.

Optional private CSV paths: `VORTEX_NEWS_CSV`, `VORTEX_NEWS_COVERAGE_CSV`, and `VORTEX_MACRO_CSV`. Their point-in-time columns and coverage semantics are those in `research_v02/vortex_v02/data.py`. Missing, unreadable or malformed external context leaves calendar/macro gates invalid and the ATLAS score unavailable. An empty event list alone is not evidence that a calendar is complete. The reader never downloads or invents calendar/macro observations.

Windows preflight now checks this v0.2 observer, and the prepared watchdog targets `observe_v02.py --observe`. Neither task registration nor the watchdog runs automatically during this preparation. Use the STOP file in the private state directory to request shutdown. No scheduled task starts the publisher or Telegram helper.

The runtime has no Mac, ChatGPT, or LLM dependency. Windows MT5 and its Python adapter are native to the VPS; cloud/dashboard/Telegram processes are optional separate consumers. Their absence or failure cannot stop the observer or its private journal. **Unattended reboot recovery is not proven:** the prepared task runs at user logon in an interactive Windows session. Automatic sign-in, credential storage, and interactive-terminal recovery after a reboot have not been configured. A future autonomy acceptance test must prove these separately; this observer is not `auto_ready` or a complete autonomous order engine.

## What is collected

The first explicitly authorized run persists a fixed history start at UTC midnight 180 days before launch. Later runs retain it. M5/M15/H1 are read through `copy_rates_range`, explicitly filtered to closed candles, checked for ascending/unique/aligned timestamps and valid values, and H4 is derived only from four contiguous UTC-aligned H1 bars. A change in the first available bar is rejected, so terminal truncation or an extended warmup cannot silently change the model's starting point.

One feature worker recomputes at most once per new M5 close. It uses the complete fixed-start frames and point-in-time external inputs. No missing market session is filled. A slow calculation leaves the latest scores stale/pending; it cannot advance their decision time. The main loop targets a heartbeat every 15 seconds and marks a quote fresh only when its actual tick time is at most 10 seconds old. Terminal calls can delay that cadence; the remote freshness checks must remain enabled. Market-data freshness is separate from calendar/macro validity.

The schema matches `cloud/README.md`. Account balance/equity/free margin/used margin and broker floating P&L are read directly. Realized/day P&L, drawdowns, profit locks, open risk, current R and managed-basket fields stay null because this collector has no execution ownership/journal with which to establish them. It lists at most 20 XAUUSD positions using session-salted SHA-256 IDs, without ticket/login values. It cannot reconstruct partial targets or pyramids from a plain position list; the basket summary remains null.

The dashboard's operational state is **FROZEN / WAIT**, kill switch true, and strategy runner mode observe. Raw engine scores are still diagnostic. Engine PASS/FAIL compares scores with the NORMAL score thresholds in the consensus direction; KIRA uses its NORMAL volatility band. These statuses do not override missing inputs, the baseline gate, or risk/execution checks. Model-selected modes/actions are recorded only in the private decision journal as **unexecuted observations**. There is no claim that an order was placed.

## Decision audit trail

`decision-journal.jsonl` is private, append-only and fsynced. Every computed closed-bar decision records model, SPEC SHA-256, UTC decision time, hashes/row counts and latest available times of the market inputs, hashes/known times of supplied external files, scores/reasons, consensus, chosen model mode/action, and `executionEnabled:false`. Changes in observer status are also appended. Duplicate decision times do not append twice. The worker checks that external files and SPEC did not change during a computation.

Every record contains previousHash and recordHash. Startup verifies the chain and stops on corruption or a partial/truncated record. The chain detects alteration within a retained journal; **it is not an externally signed timestamp**, and replacement of the entire chain or deletion of a valid suffix requires an independent backup/checkpoint to detect. Archive journal files and terminal evidence privately for a challenge audit. `cloud/` stores only the latest snapshot and is not the full archive. It does not establish a GO decision or real-account authorization.

## Private publisher

`publish_telemetry.py` defaults to an offline configuration check. The private variables are `VORTEX_INGEST_ENDPOINT` (HTTPS, no URL credentials/query), `VORTEX_INGEST_TOKEN` (64 lowercase hex), and `VORTEX_STATE_DIR`. Explicit `--publish` also requires the reviewed-baseline flag. `--once` limits it to one attempt.

Before any network transfer, it enforces the snapshot's complete nested privacy whitelist, numeric/text leaf types and ranges, demo mode, and freshness. A hidden object under a nominal numeric field is rejected locally. Tokens travel only in the Authorization header; redirects are blocked. Errors are bounded machine reasons, without endpoint/body/credential echoes. A conflicting session (409), authorization failure or other structural rejection stops the publisher for review. Transient network failure can retry the current local snapshot after 15 seconds; expired snapshots stop rather than replay indefinitely.

## Optional Telegram helper

`telegram_notify.py` is inactive by default. `--queue` only queues a meaningful local state change and sends nothing. Explicit `--send` also requires `VORTEX_TELEGRAM_ENABLE=user_enabled`, `VORTEX_TELEGRAM_BOT_TOKEN`, and `VORTEX_TELEGRAM_CHAT_ID`, all provided privately by the owner. No values have been provided or messages sent by this implementation.

Notifications contain only demo verification, connection/freshness, kill-switch state and mode. Quote changes, financial amounts, account/position IDs and arbitrary journal text are excluded. The queue holds at most 50 changes and is separate from the trading/observer loop. Before sending it persists an uncertain-delivery marker; an ambiguous response requires review rather than an automatic retry that could duplicate messages. This helper does not monitor in the background unless an operator explicitly invokes/schedules it.

## Verification

Run `python -m unittest discover -s live/tests -v` from the repository. Synthetic fake-terminal tests cover offline defaults, the baseline gate, closed candles/H4, fixed history, repeated heartbeats, account switching/redaction, stale ticks, journal recovery/tampering, and actual cloud-schema acceptance. Transport tests use fake HTTP openers; they make no network calls or Telegram messages. For the cloud-contract test, make Node available or set `VORTEX_NODE_BIN`; the test explicitly skips that one integration check if Node is absent.

Native Windows terminal behavior, the prepared PowerShell scripts, live publisher delivery and Telegram delivery have not been exercised on the VPS. Those remain gated integration work.

Primary data semantics: [MT5 copy_rates_range and UTC times](https://www.mql5.com/en/docs/python_metatrader5/mt5copyratesrange_py), [terminal initialization](https://www.mql5.com/en/docs/python_metatrader5/mt5initialize_py), [Telegram sendMessage](https://core.telegram.org/bots/api#sendmessage).
