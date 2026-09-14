# v0.2 read-only observer and private delivery

This package supports explicit private data collection; it does not claim a running VPS or an accepted deployment. The current NO-GO research result is unchanged. No code here makes a baseline pass, gives permission to use real funds, or enables execution.

`observe_v02.py` is a standalone terminal reader with no transaction/authentication API calls. It does not import the legacy execution module. Its default invocation and `--check` only validate Python imports and private configuration; they do not import MetaTrader5, initialize the terminal, create state, read the account, or start a worker. Explicit **`--collect`** permits read-only DEMO evidence collection before the baseline passes. Explicit **`--observe`** still requires `VORTEX_BASELINE_STATUS=passed_reviewed`. Both active modes require Windows. Neither mode writes that flag. It is a manual operator gate, not cryptographic proof of review; do not set it to bypass the actual baseline.

`--collect` and `--observe` are mutually exclusive. Both keep operational FROZEN/WAIT, the kill switch true, and execution disabled. `--collect --once` is a single read-only probe plus private archives; continuous collection targets one heartbeat per 15 seconds. The broker's actual current balance is recorded without resetting it to an initial budget, including losses from manual trades.

The terminal must already be signed into the expected demo account. Every snapshot checks expected identity, DEMO mode, USD currency, hedging mode, connectivity and finite account values, then checks again before writing. Failed verification produces a redacted heartbeat without account, quote, positions or v0.2 financial metrics. The code never prints identity values. `algoTradingEnabled` reports terminal state; `eaRunning:false` truthfully states that this reader is not an EA.

## Private configuration

Keep all runtime settings and files outside the repository. Required existing variables are `VORTEX_EXPECTED_LOGIN`, `VORTEX_SESSION_UTC_OFFSET_MINUTES=0`, and `VORTEX_STATE_DIR`. The offset is explicit: this v0.2 model only supports the verified Exness GMT+0 setup, while the MT5 Python API supplies UTC timestamps. An optional `VORTEX_TERMINAL_PATH` selects the installed terminal. No broker password is accepted by this reader.

Optional private CSV paths: `VORTEX_NEWS_CSV`, `VORTEX_NEWS_COVERAGE_CSV`, and `VORTEX_MACRO_CSV`. Their point-in-time columns and coverage semantics are those in `research_v02/vortex_v02/data.py`. Missing, unreadable or malformed external context leaves calendar/macro gates invalid and the ATLAS score unavailable. An empty event list alone is not evidence that a calendar is complete. The reader never downloads or invents calendar/macro observations.

Windows preflight checks this v0.2 reader offline. `Watch-Observer.ps1 -StartCollector` selects `--collect`; `-StartObserver` selects reviewed `--observe`. `Register-ObserverTask.ps1 -Apply -Mode Collect` explicitly registers a collector for the next user logon without starting it; default registration mode Observe retains its baseline gate. Defaults remain dry-run. Use the STOP file in the private state directory to request shutdown. No scheduled task starts the publisher or Telegram helper.

The runtime has no Mac, ChatGPT, or LLM dependency. Windows MT5 and its Python adapter are native to the VPS; cloud/dashboard/Telegram processes are optional separate consumers. Their absence or failure cannot stop the observer or its private journal. **Unattended reboot recovery is not proven:** the prepared task runs at user logon in an interactive Windows session. Automatic sign-in, credential storage, and interactive-terminal recovery after a reboot have not been configured. A future autonomy acceptance test must prove these separately; this observer is not `auto_ready` or a complete autonomous order engine.

## What is collected

The first explicitly authorized run persists a fixed history start at UTC midnight 180 days before launch. Later runs retain it. M5/M15/H1 are read through `copy_rates_range`, explicitly filtered to closed candles, checked for ascending/unique/aligned timestamps and valid values, and H4 is derived only from four contiguous UTC-aligned H1 bars. A change in the first available bar is rejected, so terminal truncation or an extended warmup cannot silently change the model's starting point.

One feature worker recomputes at most once per new M5 close. It uses the complete fixed-start frames and point-in-time external inputs. No missing market session is filled. A slow calculation leaves the latest scores stale/pending; it cannot advance their decision time. The main loop targets a heartbeat every 15 seconds and marks a quote fresh only when its actual tick time is at most 10 seconds old. Terminal calls can delay that cadence; the remote freshness checks must remain enabled. Market-data freshness is separate from calendar/macro validity.

The schema matches `cloud/README.md`. Account balance/equity/free margin/used margin and broker floating P&L are read directly. Realized/day P&L, drawdowns, profit locks, open risk, current R and managed-basket fields stay null because this collector has no execution ownership/journal with which to establish them. It lists at most 20 XAUUSD positions using session-salted SHA-256 IDs, without ticket/login values. It cannot reconstruct partial targets or pyramids from a plain position list; the basket summary remains null.

In collect mode, `collection/XAUUSD_M5.csv`, `XAUUSD_M15.csv` and `XAUUSD_H1.csv` retain actual closed bars with UTC times and original real/tick volume and spread fields. New bars append; an archived historical value is never overwritten if the broker later revises or truncates history. Such a mismatch is reported for review. `market-manifest.json` records hashes and row counts. H4 is derived from those H1 inputs for the model rather than represented as a separate broker feed. These files stay outside the checkout.

`collection/account-observations.jsonl` appends actual verified balance/equity/margin snapshots, or an explicitly redacted observation if account verification fails. `deals-YYYY-MM-DD.jsonl` privately preserves the current UTC day's broker deal records regardless of magic/manual attribution. Ticket/order/position IDs and comments exist only in this private archive; they are never added to status.json or the dashboard. Identical records deduplicate, while changed broker records are retained as new versions.

`accounting-latest.json` explains available accounting rather than guessing. For understood buy/sell and balance-adjustment deal types with zero credit, day-start balance is reconstructed as current balance minus all reported balance changes in the requested UTC day. Same-day deposits/withdrawals are separated as balance adjustments; `dayStartPlusBalanceAdjustments` distinguishes a funded day from an account that had no balance at midnight. Realized trading P&L includes reported commissions, swaps and fees, including manual trades. Unsupported accounting types, changing account/balance during the read, or unavailable deal history leave derived fields null with a reason. Broker history coverage is identified as the API response for the requested interval, not an independently verified account statement.

Daily **equity** drawdown remains null: deal history cannot reconstruct the intraday unrealized-equity path. The collector does not silently substitute current balance as day-start equity or treat realized loss as exact maximum drawdown. These private accounting files are inputs for a later reviewed manager; they do not populate ambiguous dashboard P&L fields or change the NO-GO decision.

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

Synthetic tests also exercise pre-baseline collect mode, preserved actual balances, manual-loss/day-start reconstruction, same-day funding separation, append-only candles, and unavailable accounting. Windows/MT5 deployment status must be established by a separate actual read-only verification; unit tests do not establish that the VPS is running. Publisher/Telegram integration remains separate from collection.

Primary data semantics: [MT5 copy_rates_range and UTC times](https://www.mql5.com/en/docs/python_metatrader5/mt5copyratesrange_py), [terminal initialization](https://www.mql5.com/en/docs/python_metatrader5/mt5initialize_py), [Telegram sendMessage](https://core.telegram.org/bots/api#sendmessage).
