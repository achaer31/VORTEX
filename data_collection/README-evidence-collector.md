# Native MT5 evidence collector

`VortexEvidenceCollector.mq5` is a read-only, long-running MT5 **Script** for private
prospective DEMO evidence. It runs inside the existing terminal without Python,
installation-policy changes, DLLs, network requests, authentication or order
submission. It does not need or enable AlgoTrading. It is not a strategy, a paper
execution engine, or proof of autonomous readiness. Local source/format checks do
not replace target MetaEditor compilation and actual terminal verification.

The exact source was compiled on the Exness terminal on 14 September 2026 with
zero errors/warnings. A running capture produced consecutive heartbeats and
closed M5/M15 bars. See [limited validation](native-validation-2026-09-14.json).
This observation does not establish strategy execution or autonomous readiness.

The defaults are inactive: `EnableCollection=false`, `ExpectedDemoLogin=0`.
Compile this source in the existing permitted MetaEditor. For an authorized DEMO
capture, enter the expected login locally and set `EnableCollection=true`.
Keep AlgoTrading off. The script checks the exact expected account, DEMO mode, USD
currency, hedging mode and terminal connection. It uses `XAUUSD` only; it does not
guess symbol suffixes, add symbols to Market Watch or change account settings.

## Private output

Each launch creates a new `MQL5/Files/VortexEvidence_<host-label>_<uptime>/` folder.
The folder contains financial values and must stay private, outside the public
repository and dashboard. Login, account name and credentials are not exported.

| File | Contents |
| --- | --- |
| `heartbeat.csv` | Sequence, `COLLECTING_ONLY` or `INVALID`, always `WAIT`, reason, host wall-clock labels, monotonic receipt counter, broker/tick time labels, bid/ask/spread/point, balance/equity/used/free margin and count of all account positions. |
| `XAUUSD_M5.csv`, `XAUUSD_M15.csv`, `XAUUSD_H1.csv` | Completed candle OHLC, broker-reported spread points, tick/real volume, nominal close, receipt label/counter, source tick cutoff and explicit gap before the bar. Timeframe values are `PERIOD_M5`, `PERIOD_M15`, `PERIOD_H1`. |
| `symbol-spec.csv` | Startup snapshot attempts after identity and quote checks: raw contract/lot/tick/stop/freeze/execution/filling/swap fields. Missing fields are `unavailable`; commission is `UNKNOWN`. This does not establish historical costs or cost verification. |

Heartbeat sampling targets five seconds. Broker history reads and disk latency can
delay a sample; no interval is fabricated to conceal a delay. Quote freshness uses
the broker's estimated server time and independently checks whether the received
tick timestamp progresses within ten seconds of monotonic time. Regressing tick
timestamps fail closed. This is a freshness heuristic, **not verification of UTC
accuracy**.

Host UTC/local labels remain explicitly unverified. Broker candle and tick labels
have an unverified server offset; none receives a misleading `Z` suffix. Nominal
candle-close times and actual receipt labels are separate. The script does not
claim a historical `available_at` or silently convert these records into the
frozen research input format.

## Collection and failure behavior

Collection starts with the bars open at the first verified fresh quote. Those bars
are recorded only after their nominal close is no later than a subsequent source
tick. Therefore a new run may have header-only candle files until the next M5,
M15 or H1 close. It does not download a historical bootstrap or make missing bars.
After interruption, newly received bars may contain explicit gaps. A candle time
is written once per timeframe/run; the cursor advances only after a complete
record and flush. A new launch starts another run rather than silently appending
to or rewriting an earlier run.

All three timeframe batches must pass read/ordering/OHLC/spread/volume checks before
that cycle writes candle data. Identity and quote checks repeat after potentially
slow reads; identity is checked again before each candle write. Data errors,
disconnect, stale quote and account mismatch produce `INVALID/WAIT` heartbeats
without quote or account metrics. No previous balance is carried into an invalid
row. Recovery requires fresh valid reads. The script does not log in, reconnect an
account, close a position or retry an order.

Symbol properties receive identity checks after each broker read and again before
the row is appended. A `capture_attempt` marker brackets each attempt with
`STARTED` and either `COMPLETE` or `INCOMPLETE_<reason>`. An account change preserves
the specific failure reason and partial attempt; it never overwrites it. After a
fresh valid identity, a retry appends a new attempt to the same file. Only a full
attempt ending `COMPLETE` is a completed snapshot; a crash can leave `STARTED`
without any end marker. Identity is checked again before the collector marks the
startup snapshot done. These checks do not make sequential broker reads atomic.

The exclusive `VortexEvidenceCollector.lock` handle blocks another collector using
the **same terminal data directory**. It is not a cross-terminal or cross-machine
lock. Existing file presence alone does not mean the lock is held. The lock and
data handles are closed on normal exit. Data files permit shared reading, but no
shared writing, so they can be inspected while collection continues. Such a copy
can end during an append or represent different moments across files: validate
complete CSV records and retain capture/receipt times. A stable stopped copy is
preferable for a final run audit. The fixed lock file remains fully exclusive.

UTF-8 records use exact byte-count checks plus a flush. A detected disk error stops
the collector; it does not continue silently dropping data. Forced termination,
power loss or storage faults can still leave a partial final record, so validate
copied CSVs before treating them as evidence. A log message is not a guarantee that
the operating system persisted data through a crash.

Stop it through MT5's script-removal/stop operation or terminal shutdown. The loop
checks `IsStopped()` frequently; a broker API call can delay return. There is no
scheduler, unattended boot, crash recovery, restart/autologin or Windows service
setup. Leaving this script running is not evidence that those behaviors work.

Calendar, DXY, US10y yield, scores, strategy entry decisions, paper fills, realized
deal history, and cloud/Telegram publishing are deliberately outside this script.
It records positions **counts**, not ownership or protective-order reconciliation.
It does not fulfill the mandatory external-data or strategy baseline gates and
cannot establish GO or AUTONOMOUS READY.

## Local contract checks

```sh
python -m unittest discover -s data_collection/tests -p test_native_collector.py -v
```

These static tests detect default/identity regressions, prohibited capabilities,
CSV column-count drift, missing redaction, cursor-before-flush mistakes and lost
freshness/spec labels. They do not execute the MQL5 runtime. Actual compiler and
terminal results must be reported separately, without publishing raw financial
records or treating synthetic/static checks as actual acceptance evidence.

The file behavior uses the documented [FileOpen flags](https://www.mql5.com/en/docs/files/fileopen)
and [FileWriteArray count](https://www.mql5.com/en/docs/files/filewritearray); UTF-8
conversion excludes the terminal null byte from
[StringToCharArray](https://www.mql5.com/en/docs/convert/stringtochararray).
The stop loop uses [IsStopped](https://www.mql5.com/en/docs/check/isstopped).
