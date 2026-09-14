# Native risk planning contract

`VortexRiskCore.mqh` is a pure planning module, version `v0.2-risk-parity-1`.
It imports no terminal APIs and makes no account, broker, order, file, network or
clock calls. It calculates a proposal from supplied facts. **Every output retains
`executionAuthorized=false`, including `allowed=true` and offline stress cases.**
`KILL` describes a planning brake; the module cannot close a position.

The references remain unchanged:
[frozen risk helper](../research_v02/vortex_v02/risk.py),
[v0.2 specification](../research_v02/SPEC.md), and the stricter
[Python DEMO manager contract](../live/README-v02-execution.md).
This module does not wire that manager or the native observer to trading.

## API

All functions use caller-owned structures; no global campaign state is stored.
Call the reset helper before populating a structure. Defaults leave verification
flags false and reject a plan. `VxrFinite` rejects nonfinite values and the MQL
`EMPTY_VALUE` sentinel; a finite sentinel is never valid market data.

| Function | Input and result |
| --- | --- |
| `VxrResetSizing(x)`, `VxrResetCampaign(x)`, `VxrResetPlan(x)` | Initialize typed facts/results to an inert state. |
| `VxrPrepareStop(entry, structuralStop, atr, side, tickSize, stop, reason)` | From an adverse entry estimate and M15 ATR, apply the structural/ATR stop rule and outward tick rounding. Return success plus stop/reason. |
| `VxrSize(facts, plan)` | Floor volume from verified cost/margin estimates for the exact supplied stop. Return an allowed/rejected size proposal. This lower-level helper does not validate context, day state or campaign ownership. |
| `VxrExactParts(lots, lotMin, lotStep, parts)` | Test whether all 25%/25%/50% portions satisfy broker minimum and step. Return false when the exact split is unavailable. |
| `VxrModeGate(dayStartEquity, equity, lossStreak, requestedMode, connected, dataFresh, protectionConfirmed, gate)` | Isolated frozen mode helper. Return mode, reason, risk fraction and drawdown. |
| `VxrPlanCampaign(facts, plan)` | Apply mandatory fact gates, persistent brakes, current margin allocation, base/add rules and nominal/open-risk caps, then call sizing. This is the composite planning boundary. |

`VxrFloorLots` and `VxrRoundPrice` are exposed arithmetic helpers. An adapter must
not use successful low-level arithmetic as a substitute for the composite gates.

`VxrPlan` contains `allowed`, `reason`, `mode`, `exitPolicy`, `lots`, `riskCash`,
`margin`, `budget`, `minimumRisk`, `stop`, `riskFraction`, `tp1Lots`, `tp2Lots`,
`runnerLots`, `campaignNominalAfter`, `campaignOpenRiskAfter`, `addLevel`,
`stressOnly` and `executionAuthorized`. A rejection resets numeric outputs to zero
and the mode to FROZEN, except an explicit KILL result. `min_lot` also preserves
the cash budget and minimum-lot risk as diagnostics. Zero output on rejection is
not evidence that actual account risk or margin is zero. Low-level successful
`VxrSize` leaves mode FROZEN because it has no mode input.

## Required facts and units

`VxrSizingFacts` supplies side (`1` long or `-1` short), digits, current equity,
risk fraction/cap, adverse entry, already-rounded stop, minimum/maximum/step lot,
tick size, broker minimum stop distance, raw broker free margin, margin allocation
fraction, loss per lot, cost reserve per lot and margin per lot. Metadata, loss
and margin estimates each need a separate true validity flag.

Prices and stop/spread distances use XAUUSD price units, not point counts. Money
must use one verified account currency; the intended adapter must establish DEMO,
USD and hedging identity itself. Equity is the supplied current value: the kernel
never resets it to a starting balance or assumes new funds are trading profit.

The loss estimate is for the **exact supplied rounded stop** and includes the
configured adverse stop slippage. Separate `costReservePerLot` covers costs not
already included, such as both-side commission. Do not count a cost twice or
silently omit an unknown fee. `marginPerLot` is a separately verified estimate.
The fixtures use linear USD estimates; an actual adapter must use broker
calculators and recheck the final proposed volume, since linear scaling alone
does not establish actual margin, tiering or liquidation cost.

`VxrCampaignFacts` adds:

- A reconstructed day-start equity, loss streak and persistent freeze/kill and
  EXTREME-disabled flags. These are supplied ledger facts, not reconstructed here.
- Connection, data, quote, decision freshness, signal readiness, news validity and
  blocking, macro/session validity and protective-order confirmation.
- Capital provenance, reconciliation, ownership and pending-intent state. An
  unresolved intent blocks planning; this module neither clears nor retries it.
- Campaign count/side/start equity, nominal risk already reserved, current open
  planned risk and a validity flag. Locked gains must not offset another leg's
  positive risk to justify a larger add.
- For additions, base-open status, confirmed cost breakeven for prior legs,
  strictly profitable current legs, closed-bar gain in R and signed consensus,
  ORION and NOVA scores in `[-100,100]`.
- M15 ATR, actual spread, adverse entry and executable liquidation price. The
  latter must be on the loss side of entry with the SL outside the spread and
  broker minimum stop distance.
- **All account used margin**, with `marginAllocationValid=true`. `sizing.freeMargin`
  remains raw broker free margin. Available new margin is the smaller of that
  value and `max(0, equity * min(maxMarginFraction, 0.25) - usedMargin)`.

Unknown history, identity, protection, costs, context, current risk or margin must
remain unverified. A caller setting a flag is an assertion; the kernel cannot
prove it. Manual losses and capital changes must remain in the reconstructed
account/day evidence, and restarting must not create a new day anchor.

## Rules calculated

Initial stop distance uses the greater of the structural candidate distance and
1.4 times M15 ATR, measured from the adverse entry estimate. The structural
candidate is already 0.1 ATR beyond invalidation. Stops round outward; a final
distance above 2.2 ATR is rejected. The composite also rejects actual spread above
the smaller of 0.60 and 0.10 ATR, stale inputs and an SL inside the current spread
or broker stop limit.

Sizing floors affordable volume to the broker step and never raises it to the
minimum. An unaffordable minimum returns `min_lot`. Costs and margin are reserved
before acceptance; a volume that fails the margin gate is rejected. Final planned
risk cannot exceed its cash budget.

The baseline NORMAL/AGGRESSIVE/EXTREME fractions are 2%/3.5%/5% of current equity.
`CAP_NORMAL` and `CAP_AGGRESSIVE` cap those fractions at 2% and 3.5%; they do not
rename the voted mode. `STRESS_075` and `STRESS_10` change only EXTREME to 7.5% and
10%, require `researchStressPermitted=true`, and are marked stress-only. These
research profiles do not relax the Python DEMO manager's baseline-only policy.

After two losing campaigns, new base/add risk halves and EXTREME is unavailable.
Three losses or a supplied persistent freeze blocks new plans. Daily equity at
or below 90% of its day anchor disables EXTREME; at or below 85%, or a supplied
persistent daily kill, returns KILL. Persistence and actual liquidation are the
adapter's responsibility.

One base campaign may receive at most two same-direction additions. Add 1 requires
closed gain at least +1R and signed consensus at least 78. Add 2 requires +2R,
consensus at least 82 and signed ORION/NOVA at least 80. Earlier cost breakeven
must be confirmed; every leg must still be strictly profitable. Nominal add risk
is 1.5% then 1%, subject to the two-loss reduction. The planner contains no
martingale, loser averaging, opposite-side campaign or extra-add path.

Cumulative nominal budgets are capped at 7.5% of campaign-start equity, and summed
open planned risk at 7.5% of current equity. Only the explicitly permitted 10%
stress profile uses 10% caps. A 7.5%/10% base already consumes that profile's whole
nominal cap; it receives no additional allowance merely because its lot rounded
down. Total used plus proposed margin stays within the supplied allocation,
capped at 25% of current equity.

An executable exact split returns `partial_25_25_50`; otherwise the unchanged lot
returns `single_trailing`, including an affordable minimum lot. The result is
only an allocation. The frozen exit behavior still requires a separate adapter:
TP1 +1.5R, TP2 +2.5R and an SL-protected runner without a fixed TP for the split;
full +2.5R TP for the single-position fallback; cost breakeven after +1R; single
trailing after +1.5R, and split runner trailing only after confirmed TP2 closure.
The kernel does not produce target prices, move SLs or confirm partial fills.

## Reviewed fixes and declared differences

The independent review reproductions now reject an addition that would take
existing plus new margin above the allocation, and reject signed pyramid scores
outside `[-100,100]`. Missing used-margin facts also reject. Price rounding uses
a canonical decimal representation and an outward comparison, preventing an
unnecessary extra tick from an integer-minus-epsilon division. These fixes do not
change the frozen strategy thresholds or expected historical results.

This is not a claim of identical behavior for every possible Python input:

- Native volume/tick precision is bounded to eight decimal places and finite
  integer-unit ranges. Arithmetic overflow, sentinel values and unsupported
  precision reject.
- Native double floor can conservatively underfloor at decimal edges: `.3/.1`
  can yield `.2` lots and `.6/.2` can yield `.4`. These are explicit native-policy
  fixtures, distinct from the frozen Python `Decimal` oracle. Available volume
  is never increased by epsilon.
- `VxrSize` requires a pre-rounded stop and verified calculator facts. The frozen
  offline helper rounds internally and calculates a linear contract estimate.
  Rejecting an off-grid stop protects the supplied loss-estimate basis.
- The isolated mode helper preserves the frozen floating drawdown formula. The
  composite additionally applies conservative exact cash comparisons at 90%/85%
  of day-start equity and requires persistent state facts.
- Composite context, ownership, capital, score-domain and aggregate-margin gates
  are explicitly additional validation, not one-to-one frozen-helper parity.
  The native size helper rejects a margin failure instead of implementing the
  Python live manager's optional downward search; it never increases the margin
  allocation to force acceptance.

## Validation status

Frozen risk source SHA256:
`fd37290750cd4faee5f1fc325ec9aef4b1be0effdb1aeaa5e40b10f530c3579a`.
Target MetaEditor compiled the current risk harness/core with **0 errors and
0 warnings** (2,773 ms). The separate comparator of actual native output returned
**PARITY_PASS: 155 cases, zero differences**, with 1,433 numeric comparisons and
maximum absolute error `1.1102230246251565e-16`. The five staged input files were
hash-checked separately. The [sanitized native risk record](validation-native-risk-2026-09-14.json)
retains the source, transport and output evidence.

The independent fixture set contains 155 cases: 36 size, 24 mode, 78 campaign and
17 stop. All match a translated exact-source C++ arithmetic check with the
comparator's tolerances, and the two review reproductions reject. That earlier
check is separate from the now-recorded native result. See the
[fixture and comparator contract](tests/risk_readme.md) for generation, transport,
oracle scopes and acceptance criteria.

No case establishes current broker metadata, fee/history completeness, a passed
strategy baseline, profitability or approval to execute. Native order submission,
protection management, durable recovery and observer-to-execution wiring remain
unimplemented by this module.
