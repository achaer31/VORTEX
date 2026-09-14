# VORTEX v0.2 — autonomous runtime contract

**Current status: NO-GO; AUTONOMOUS READY has not been demonstrated.**
The requirement is fixed: runtime decisions are deterministic code on the VPS,
without an active MacBook, browser, ChatGPT/Astra session or mandatory LLM/API.
Astra is a developer for build, test, audit, debugging and reviewed updates.

```text
Broker market data + point-in-time external feeds
                     ↓
      ORION / VORTEX / NOVA / LUNA / KIRA / ATLAS
                     ↓
          Consensus + deterministic mode selector
                     ↓
          INDEPENDENT RISK GATE (highest authority)
                     ↓
       Sizing + execution + confirmed broker SL/TP
                     ↓
               Broker account

Journal / health ──→ optional publisher ──→ DB ──→ mobile dashboard
              └──→ optional alert queue ──→ Telegram
```

Dashboard, database telemetry and Telegram availability must not gate local
risk management, protective stops, or journal writes. The local durable journal
and execution reconciliation are mandatory; if their integrity is unknown,
new orders stop. External calendar/macro are data dependencies, not LLM advice.
Any future optional intelligence layer is outside this deterministic decision
path and cannot override sizing, stops, kill switches or account/environment.

## Implemented versus pending

| Layer | Current evidence |
|---|---|
|6 engines, H4/session/news interfaces, independent risk | Implemented, synthetic tests + frozen historical run |
|Adaptive exits, SL/trailing, max2 winner adds, brakes | Implemented in offline simulator; not yet integrated as v0.2 broker manager |
|Windows MT5 v0.2 reader | Implemented and fake-terminal tested; not started on VPS |
|Generic demo execution adapter | Synthetic lifecycle tests; legacy entry/arming hardblocked |
|Private publisher, optional Telegram helper | Implemented, fake transport tests; no real deliveries |
|Database/Edge/HTTP auth | Implemented and local SQL/HTTP tested; no remote provisioning |
|Docker/Postgres/telemetry/watchdog | Prepared template; Docker runtime absent locally, not launched |
|Mobile web | Backtest report + disconnected monitoring surface; source data is explicit |
|Full VPS execution/restart/Mac-off acceptance | NOT TESTED; not AUTONOMOUS READY |

The current reader's operational state remains FROZEN/WAIT; model decisions are
unexecuted diagnostic journal entries. Reading scores is not equivalent to
managing a position. Do not connect the simulator to live sends without the
separate broker state machine and acceptance checks being completed.

## Windows and Docker boundary

MT5 terminal and its official Python bridge run natively in the Windows VPS
user session. A Linux Docker image does not make Windows MT5 headless. Docker
templates cover the separate database/HTTP/telemetry/watchdog services, which
can live on a suitable server. This preserves the small2GB VPS for the terminal
and engine; do not assume every container fits or virtualization is supported.

The prepared scheduled task starts at **user logon**, not proven unattended
boot. Unattended restart is still a blocker: login/session recovery, terminal
startup and restart reconciliation must be proven on the actual VPS. No
automatic sign-in, stored Windows passwords or weakened security is configured.

## Required restart state machine for final execution integration

1. Acquire the single-process lock and verify immutable account/model fingerprint.
2. Recover and validate durable journal/state. Unknown or partial writes freeze.
3. Verify DEMO/account identity and broker connection; read positions, pending
   orders and deal history. API errors are UNKNOWN, not empty lists.
4. Reconcile pending intents, fills, volume, ownership and protective SL/TP.
   Do not replay ambiguous sends or adopt manual positions. Missing protection
   requires the defined emergency handling before any new risk.
5. Restore equity/risk budget, streak, daily drawdown and kill status without
   treating a restart as a fresh$50 allocation or clearing a freeze.
6. Once complete, load fresh closed-bar/mandatory external inputs and only then
   seek new setups. Missing/stale/disconnected/ambiguous means FAIL-SAFE/WAIT.

The generic scaffold tests some lifecycle safeguards; full v0.2 recovery with
partial exits/pyramids remains a required integration milestone. Baseline GO and
AUTONOMOUS READY are separate. Neither a config flag, service process, successful
deployment nor target date can substitute for their evidence.

## Explicit acceptance

Use the evidence gate in `deploy/autonomy/` after baseline review. The operator
must actually disconnect the MacBook/RDP and close the Astra session during an
observed VPS interval, then retain independent VPS/broker timestamps, heartbeat,
decision and position-management evidence. Also test process crash and full VPS
restart, plus dashboard/Telegram outage. Verify restored protective orders and
reconciliation precede any entry. A WAIT-only run proves only the exercised
path; it cannot prove unexercised SL/TP, adds or recovery behavior.

Do not turn off the user's MacBook automatically from this development session.
The final test must be scheduled with the owner when the eligible demo system
exists. Current missing inputs and zero trades prevent statistical baseline GO.
