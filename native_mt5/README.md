# Native MT5 port: offline parity and read-only observation

This is an implementation-validation stage. `VortexSignalCore.mqh` ports the
frozen v0.2 indicator/feature calculations, six engine scores, consensus and pure
mode voting to supplied arrays. `VortexParityCheck.mq5` compares that implementation
through locally staged **synthetic** fixtures. `VortexNativeObserve.mq5` is a separate
DEMO-only observation wrapper. None of these files is a trading activation.

The risk and execution adapters have **not** been ported here: no lot sizing,
margin reservation, fills, partial exits, pyramids, protective-order management,
daily-loss enforcement or broker reconciliation is implemented by this package.
Parity is not strategy profitability, a passed baseline, GO, or AUTONOMOUS READY.
The frozen Python sources and historical reports remain unchanged.

Declared versions are `VORTEX-NATIVE-PARITY-0.1` for the harness and
`v0.2-parity-1` for the core. A version label is not proof that a particular binary
was built from matching bytes. Target MetaEditor logs, exact source hashes, native
output and comparator results are retained separately from generated expected CSVs.

## Verified evidence — 14 September 2026

The harness was compiled in the Exness VPS MetaEditor with **0 errors and 0
warnings**, then executed against the staged synthetic fixtures. The separate
Python comparator returned **PARITY_PASS** for **9 scenarios, 8,685 signal rows
and 22 pure mode cases**. Its manifest, row counts, missing values, discrete
outputs and numerical tolerances passed. The
[sanitized parity record](validation-native-parity-2026-09-14.json) retains
source and output hashes; compiler/run provenance is separate evidence.

The separate observation wrapper also compiled with **0 errors and 0 warnings**
(2,924 ms). Its MQL file property is `version "1.00"`; that packaging field does
not rename the frozen strategy or core version. Its observation and expected-DEMO
inputs were configured, and Start was submitted in MT5 with Allow Algo Trading
unchecked. The local Mac then locked before the remote journal could be read;
automatic unlock failed. **Observer operation remains unverified.** The
[target validation record](validation-target-2026-09-14.json) records the attempt,
source/transfer/compiler-log hashes and this blocker. A submitted Start action
does not prove continued operation or unattended recovery.

All **29 local native tests** passed: 11 harness contracts, 6 observer contracts
and 12 fixture/comparator tests. They are source/synthetic checks, separate from
the observed native run and its parity comparison.

The research baseline remains **NO-GO / NOT_EVALUABLE**. The wrapper has
no verified calendar coverage, DXY/US10y or session adapter for ATLAS and the
mandatory context gates; missing inputs continue to require **FROZEN / WAIT**.
The native risk/execution adapter is absent. No order, strategy-profitability
claim or autonomy acceptance follows from this parity result.

## Offline harness

Place `VortexParityCheck.mq5` and `VortexSignalCore.mqh` together in the target
terminal's Scripts source folder, then compile the harness in MetaEditor. This
script has no account, quote, terminal-history, indicator-handle, network,
authentication or order calls. Its only runtime inputs are staged CSV files and
its two script inputs. `GetTickCount64()` names its output folder; it is not used
as a market clock or decision timestamp. It does not touch the collector's lock
or files and can run on a separate chart.

`EnableOfflineParity=false` is the default and opens no files. `FixtureDirectory`
is one relative folder name under `MQL5/Files`, containing only letters, digits,
underscores and hyphens, with length 1–48. Paths, dots, `..`, separators and named
pipes cannot be supplied. Case IDs use the same restricted grammar.

Generate fixtures with the unchanged Python implementation on a machine where its
runtime is available; do not alter Windows installation policies for this step:

```sh
python native_mt5/tests/parity_fixtures.py /private/path/vortex-parity-fixtures
```

The generator refuses to put its large generated dataset inside this repository.
Stage the generated input files into, for example,
`MQL5/Files/VortexParityFixtures/`. The folder layout is fixed:

| File | Contract |
| --- | --- |
| `fixture_kind.txt` | First line exactly `SYNTHETIC_OFFLINE_PARITY_V1`. This is a declared test marker, not market-data provenance. |
| `cases.csv` | Header `case_id`, one unique safe ID per scenario. |
| `<case>_M5.csv`, `<case>_M15.csv`, `<case>_H1.csv` | `epoch_utc,open,high,low,close,tick_volume,spread_points,real_volume`; ascending UTC bar opens. H4 is derived inside the kernel, not supplied separately. |
| `<case>_external.csv` | `decision_epoch,news_valid,news_blocked,macro_valid,session_valid,session_ideal,dxy_roc,us10y_change,asia_high,asia_low,london_high,london_low,newyork_high,newyork_low`. Header-only deliberately supplies no external context. |
| `mode_cases.csv` | `case_id,orion,vortex,nova,luna,kira,atlas,consensus,h1_alignment,h4_alignment,session_ideal,eligible`. These cases exercise pure voting separately from indicator generation. |

Fixture CSV inputs are machine-generated, unquoted numeric/identifier fields.
Boolean fields are exactly `0` or `1`; optional missing numeric values are empty,
never literal `NaN`, infinity or an invented zero. Required prices/counts/times
must be valid numbers; count fields must be integral. An ordinary trailing newline
is accepted. Limits are 32 scenarios, 50,000 rows per timeframe/external file,
512 mode cases and 32 MiB per input file. Bad schemas, duplicate IDs/times, unsafe
paths or invalid numbers fail closed.

Run with `EnableOfflineParity=true` after staging the explicitly synthetic input
folder. Every run creates a new `MQL5/Files/VortexParityResult_<monotonic-counter>/`
directory. It never overwrites an earlier result directory. The output contains:

- `<case>_signals.csv`: one row per supplied M5 bar, with decision/context-close
  epochs, six scores and reasons, consensus, ATR, structural stops/swings, mode,
  signal, H1/H4 alignment, context freshness, execution-valid and ready flags.
- `mode_results.csv`: case ID, mode and signal from pure voting fixtures.
- `manifest.csv`: declared source versions, synthetic/offline scope, requested and
  completed counts, any error, `parity_evaluated=false` and `strategy_approval=false`.

Missing native numeric values serialize as empty CSV fields. A zero context-close
timestamp means no available higher-timeframe row, so it and its corresponding
H1/H4 alignment are empty. Alignment `0` on an existing warm-up context remains a
real zero. Reason strings and flags must match exactly; they are not interpreted
as recommendations.

The harness only reports `COMPUTED_FOR_COMPARISON` or `FAILED`. It does not inspect
the Python expected files or label its own result a parity pass. A stopped run or
disk failure can leave partial output and must not be accepted as a complete run.

Copy the finished native output to the machine containing the original generated
fixtures and run the comparator:

```sh
python native_mt5/tests/compare_parity.py \
  --fixtures /private/path/vortex-parity-fixtures \
  --actual /private/path/VortexParityResult_run \
  --report /private/path/native-parity-report.json
```

The comparator verifies fixture hashes, output schemas, row order/identity and
missingness. It requires a complete native manifest with matching versions/counts.
Numeric comparisons use its declared absolute `1e-7` and relative `1e-10`
tolerances; discrete values/reasons match exactly. These are numerical tolerances,
not parameter adjustments to make a strategy profitable. Preserve mismatches and
fix implementation defects; never edit expected results to disguise a difference.

## Exact test coverage and limits

The initial generator defines nine deterministic scenarios: upward trend,
downward trend, quiet prices, changing volatility, zero ATR, missing bars,
initially absent higher-timeframe context, external-input/spread edge cases, and
entirely missing external context. It also defines 22 pure mode cases covering
long/short NORMAL, AGGRESSIVE and EXTREME voting, KIRA boundary/missing values,
ineligibility, minimum ORION/NOVA checks, mixed alignment and opposing LUNA.
The generated `python_reference_manifest.json` records actual row counts, reasons,
readiness, modes, flags and frozen reference source hashes for that fixture build.

The fixture pipeline exercises EMA/Wilder-derived indicators, higher-timeframe
close availability/freshness, H4 construction, confirmed structure/sweep state,
engine outputs and final voting. It does not enumerate every floating-point input,
every threshold boundary, every possible event sequence or every broker condition.
Direct mode cases do not prove that a complete real-data indicator pipeline can
produce each mode. A translated-language smoke check is not an MQL5 execution test.

The native kernel is intentionally strict about exact timeframe alignment,
nonnegative epochs/real volume, numeric overflow and a complete derivable H4
history. Some invalid inputs accepted by an isolated Python helper may therefore
be rejected before native calculation. The caller must supply UTC-labelled,
already-closed XAUUSD bars for the frozen point-size assumption of `0.001`, plus
causal external context. The core does not fetch data, determine historical
timezone offsets or calculate session/DST availability itself.

## Separate bounded-history DEMO observer

`VortexNativeObserve.mq5` remains disabled by default and requires a locally entered
expected DEMO login, USD currency and hedging mode. It reads existing XAUUSD data,
checks completed bars and quote/identity freshness, and writes a private journal.
It does not log in or change the account, enable AlgoTrading, submit orders or
publish financial data. Its lock is distinct from the evidence collector's lock.

The current wrapper requests the most recent **600 M5, 600 M15 and 1,000 H1 bars**
on each new M5 decision and recalculates from those bounded windows. EMA/Wilder
seeds and confirmed structure/sweep state therefore restart at each window's
beginning. As the windows move, their initial seeds change. This is not equivalent
to preserving the original full-history state or the frozen 180-day backtest.
Successful offline parity on identical fixture arrays does not prove full-history
equivalence for these different live input windows.

The observer journal also is not a replay bundle: it does not archive every one
of those bootstrap arrays with per-decision source hashes. The separate collector
starts with newly completed candles, so its first records alone cannot reconstruct
all of this observer's earlier warm-up history. Treat logged scores as bounded
read-only observations, not independently reproduced trading evidence.

No runtime calendar/coverage, DXY, US10y yield, session/DST or adaptive data adapter
is connected to this wrapper. It passes an empty external array, so mandatory
context stays invalid and output is explicitly **FROZEN/WAIT**, with no execution
adapter. It never manufactures external scores or converts missing context into
permission to trade. It assumes the broker server is UTC+0 and checks consistency
against the host clock; that comparison is not an independent UTC attestation.

Stopping the script or closing the terminal ends observation. Neither the wrapper
nor the parity harness establishes reboot recovery, a Windows service, unattended
startup, Mac-disconnection endurance, broker reconciliation or autonomy readiness.
