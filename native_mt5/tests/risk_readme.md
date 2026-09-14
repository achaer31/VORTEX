# Synthetic native risk comparison

These tools compare pure native risk arithmetic with the frozen Python reference and separately test declared additional safety rules. They never connect to a trading terminal or authorize an order. The `.mq5` harness reads synthetic files only and is disabled by default.

## Verified native result — 14 September 2026

The actual MQL5 run passed all **155 cases**: 36 size, 24 mode gate, 78 campaign, and 17 stop cases. Independent comparison found zero differences across 1,433 finite numeric pairs; maximum absolute difference was `1.1102230246251565e-16`. The compiler log records zero errors, zero warnings, and 2,773 ms elapsed.

All five installed input hashes (four CSV files and the synthetic marker) match the frozen fixture set. A separate check of all 155 raw result rows confirmed sizing, partial-exit allocation, cash-budget, aggregate-margin, ATR-stop, loss-state and pyramid constraints. The tested source SHA-256 values are `fd37290750cd4faee5f1fc325ec9aef4b1be0effdb1aeaa5e40b10f530c3579a` for the core and `27c08373532e816d26fa635ee0dbab9309ee8936bfbc2a1eef4a38ed6c7d4a53` for the harness. See the [sanitized proof](../validation-native-risk-2026-09-14.json).

This is synthetic arithmetic and safety-rule verification. It does not establish profitability, live execution readiness, or authorization to place an order. The explicitly labeled additional safety and decimal-floor policies below remain distinct from frozen Python parity.

`risk_fixtures.py` generates four CSV families outside the repository. Low-level size and mode expectations come directly from `research_v02/vortex_v02/risk.py`. Stop preparation combines the documented ATR policy with frozen tick rounding. Successful campaign sizes use the frozen size calculator with explicitly prescribed mode or pyramid fractions. Campaign rejection cases declare isolated safety rules; they are **not** advertised as a function-by-function port of the Python helper.

Covered cases include minimum lot rejection, downward size rounding, adaptive 25/25/50 versus single-position exits, 2%/3.5%/5% sizing, explicitly permitted offline 7.5%/10% stress profiles, consecutive-loss controls, daily drawdown, required market/context/ownership flags, positive-only pyramids, confirmed breakeven, and two-add limits. All account values in the fixtures are hypothetical. Stress results never authorize deployment or trading.

The raw frozen mode helper retains its binary floating-point calculation at the exact 10% daily-drawdown boundary. The composite native planner additionally compares cash against 90%/85% of day-start equity. That conservative refinement is a separately named case; the frozen reference stays unchanged. Two other explicit native-policy cases document conservative floating-point underflooring at `.3/.1` and `.6/.2`; they are not labeled exact Decimal parity. The composite planner includes existing used margin in its total allocation limit, and rejects pyramid vote values outside the score domain.

## Local generation and tests

From the repository root, with the research Python dependencies installed:

```sh
python -m unittest discover -s native_mt5/tests -p 'test_risk_tools.py'
python native_mt5/tests/risk_fixtures.py /path/outside/repository/risk-fixtures
```

Generation creates a new directory and refuses an existing one. Inputs use exact headers, plain ASCII case IDs/enums, numeric CSV values, and empty numeric cells for deliberately missing facts. No account identifier or credential belongs in these files. The JSON reference manifest records frozen source hashes, every input/expected-output file hash, case counts, and each case's oracle scope.

## Native synthetic run

An operator may compile `VortexRiskParityCheck.mq5` alongside `VortexRiskCore.mqh` in MetaEditor. Compilation and a native run are separate evidence from Python tests. Copy only the four `risk_*_cases.csv` inputs and `fixture_kind.txt` to one safe folder under `MQL5/Files`. Run the script with `EnableOfflineRiskParity=true` and that folder's name in `FixtureDirectory`. Paths, account settings and orders are not accepted as inputs.

The script creates a new `VortexRiskParityResult_<counter>` folder containing four result CSV files and `manifest.csv`. `COMPUTED_FOR_COMPARISON` means computation completed; it does not mean parity passed. Stop/error/partial-output states are rejected by the comparator.

```sh
python native_mt5/tests/risk_compare.py /path/to/risk-fixtures /path/to/native-result --out /path/to/private-comparison.json
```

The comparator requires matching versions, complete unique case IDs in order, all reference hashes, exact boolean/string/integer values, and finite numeric values. Missing and zero differ. Nonzero floats use relative tolerance `1e-10`, absolute tolerance `1e-9` (allocation fields `1e-12`); zero remains exact. An accepted plan whose reported risk exceeds its cash budget is rejected regardless of numeric tolerance. Any mismatch returns a nonzero process status and retains case/field details and oracle scope. It never silently relabels a failed case as a pass. Native input transport and compiled-source provenance require separate operator evidence.

## Limits

The native kernel receives loss/margin estimates for the exact supplied rounded stop. These fixtures use a linear USD estimate, not actual broker calculators. Identity verification, quote freshness, metadata validity, news/macro coverage, reconcile state and protective-order confirmation are synthetic assertions. A passing arithmetic comparison proves none of those runtime facts.

The planner does not implement order transmission, partial-close execution, trailing stops, recovery, or a live campaign manager. Existing minimum lot, margin and stop limitations still apply to any small account. Neither parity nor a stress scenario establishes a profitable strategy, a baseline pass, or autonomous readiness.
