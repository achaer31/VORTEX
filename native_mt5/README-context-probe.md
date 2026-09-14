# Native context discovery, not a data adapter

`VortexContextProbe.mq5` is a one-shot, read-only script for the existing MT5
terminal. It identifies narrowly matched symbol labels and checks a bounded USD
calendar query. An actual target run completed on **14 September 2026**. The copied
private manifest and candidate rows were independently checked; the
[sanitized validation record](validation-context-probe-2026-09-14.json) contains
their hashes and the precise limits. Compilation/run provenance is separate from
this file-content audit; raw captures remain private.

The manifest reports **357 catalog names examined**, with two matched symbols and
no property errors. All **24 persisted property rows** have complete fields and a
contiguous sequence. DXY is described as “US Dollar Index” and reports calculation
mode `4`. MetaQuotes' [official enum example](https://www.mql5.com/en/book/automation/symbols/symbols_margin)
maps that number to `SYMBOL_CALC_MODE_CFDLEVERAGE`. This is a leveraged CFD
calculation mode; it does **not** establish an approved ICE DXY spot feed.

The other match, **USDXOF**, is described as “US Dollar vs West African CFA” with
profit currency XOF. It matched the `USDX` substring and is a **false positive**,
excluded as a dollar-index input. There was no ten-year keyword candidate. Only
matched metadata was persisted, so this is not an independent replay of all
357 names or proof that every differently named feed is absent.

The USD calendar returned **two low-impact value records**, zero high-impact
records and zero API/metadata errors for server labels **2026-09-14 08:59:57 to
2026-09-15 09:59:57**. Host/server labels agreed at the sampled second, but UTC
accuracy remains unverified. The reported elapsed counter was 0 ms; that does not
establish zero latency or feed freshness. Coverage, news/macro validity,
historical availability and strategy approval all remain **false**. No normalized
context files were created, and the previous rejected calendar capture was not
altered.

Default `EnableContextProbe=false` and `ExpectedDemoLogin=0` stop before account
reads or files. An explicitly enabled run requires the expected connected DEMO
account, USD currency, hedging mode and execution outside Strategy Tester. The
login is checked but never printed or persisted. Identity is checked before and
after property/API reads, before every candidate row and at manifest completion.
No balance, equity, positions, deals, passwords or access tokens are read.

Compile this standalone file with the installed MetaEditor. On a separate chart,
enter the expected DEMO login privately and enable only `EnableContextProbe`.
Leave Allow Algo Trading unchecked. This script does not log in, place or check
orders, change Market Watch, read price history, open sockets, call WebRequest,
change permissions, or access the observer/collector lock. A fixed exclusive
`VortexContextProbe.lock` blocks concurrent copies in the same terminal data
directory. Closing/removing the script stops it; no restart/service claim applies.

## What it captures

The private output is a new `MQL5/Files/VortexContextProbe_<host-label>_<counter>/`
directory, with no user-configurable output path. Files permit readers but have
one writer. UTF-8 byte counts and flush results are checked; disk failure stops
output. Never use partial copies or a manifest lacking final
`manifest_complete=true` and `identity_valid_at_manifest_end=true`. An INVALID
run may retain earlier provisional candidate rows; discard it as a complete
inventory and repeat only after its actual cause is resolved.

`candidates.csv` contains long-form property rows with an unverified host receipt
label, monotonic receipt counter, category, symbol, field, value, availability,
API error and discovery-only scope. Names/descriptions are matched against DXY,
USDX, dollar-index and specific US/Treasury ten-year/yield labels. A possible
futures, CFD, custom symbol or another country's yield remains a candidate;
neither the name nor the category certifies its underlying instrument.

Properties include description, selected/custom flags, calculation/trading/chart
modes, digits, point, contract size and base/profit currency. No quote is sampled
or converted into a macro value. Unavailable fields stay blank with their error.
The [official enumeration API](https://www.mql5.com/en/docs/marketinformation/symbolstotal)
and [name API](https://www.mql5.com/en/docs/marketinformation/symbolname) support the
general catalog; [property reads](https://www.mql5.com/en/docs/marketinformation/symbolinfostring)
may fail for an unselected symbol. The probe never selects it to hide that failure.
Only names and available descriptions are searched, so zero matches do not prove
the broker has no relevant feed under a different name or inaccessible description.

The catalog scan is bounded to 10,000 names, 100 candidate symbols and a checked
60-second scan budget. Duplicate names or a changed total fail the scan; these
checks are not an atomic broker-catalog snapshot. The calendar query has its own
10,000-row bound. An individual native API call may block until MT5 returns;
the scan budget is not a guaranteed timeout for a calendar/network service.

`manifest.csv` records catalog counts/errors and the calendar's return code,
returned value count, examined metadata count, importance counts, ambiguous
high-impact times and values outside the requested interval. Calendar counts are
value records, not unique event definitions. No event titles, links, IDs, actual
economic values or forecasts are exported. `DISCOVERY_COMPLETED_WITH_ISSUES`
means inspect the errors; it never means complete news coverage.

The [calendar API](https://www.mql5.com/en/docs/calendar/calendarvaluehistory)
uses trade-server times. The query spans the server's previous hour through its
next 24 hours. The probe records adjacent host/server clock samples, the server's
last quote time, and receipt after all calendar metadata lookups. A difference
within ten seconds is only `CONSISTENT_UNVERIFIED`; a comparison between clocks
cannot verify UTC accuracy or establish historical server offsets. No timestamp
is silently promoted to a verified UTC `available_at`.

## Audit of the existing contracts and remaining blockers

The existing [calendar exporter and ingestion validator](../data_collection/README.md)
already preserve receipt after event metadata, query errors and unattested coverage.
The actual earlier capture remains rejected for unverified host UTC; this probe
does not rewrite it or change that result. An empty successful news query is not
positive evidence that every USD high-impact event is covered.

The frozen Python contract requires `news.csv` with event/known times and USD/high
classification, plus independently reviewed `coverage.csv` spanning the entire
decision's inclusive ±10-minute exclusion window. Prospective coverage review
cannot be backdated. The current ingestion validator limits its reviewed coverage
lease to five minutes from capture and keeps unreviewed coverage empty.

Macro requires documented **ICE DXY spot index points** and **US Treasury ten-year
yield in percent per annum**, with two actual observations for change. Each must
have actual observation and receipt records. The paired `available_at` is the later
receipt; paired `observed_at` is the older component. The frozen gate requires that
older observation to be at most 60 minutes old when the decision is made. A fresh
DXY tick cannot refresh stale yield data. USDJPY, another dollar basket, futures
prices, bond prices, daily Treasury figures and guessed TNX scaling are not
substitutes. Review the [primary source/access inventory](../data_collection/README.md#primary-sources-and-remaining-access-questions).

The Python observer consumes only its explicitly configured external files and
checks their digests around calculation; collection does not create missing macro
or news evidence. The native observer still supplies empty external context.
Session membership and levels additionally need a deterministic, causally tested
UTC/DST/session adapter; a list of broker symbols cannot supply it.

These facts can guide a future deterministic adapter only after the actual probe
output is reviewed, instrument mappings/units/entitlement and update cadence are
documented, clock provenance is resolved, and prospective receipt logs are
collected. If MT5 has no suitable spot-index/yield feed, an authorized primary
provider or entitled vendor feed remains a separate blocker; this probe buys,
connects to or configures none. Historical `available_at` and 60-day unseen
coverage cannot be inferred from today's inventory.

Every manifest fixes `coverage_attested`, `news_valid`, `macro_valid`,
`historical_available_at_proven`, `execution_enabled` and `strategy_approval` to
false, with action WAIT. No normalized adapter input is emitted. Existing
observer/core, frozen research, baseline NO-GO and autonomy NOT_READY are unchanged.

Run the static checks locally with:

```sh
python -m unittest discover -s native_mt5/tests -p 'test_context_probe_contract.py' -v
```

These inspect source boundaries and failure paths; they are not native compiler,
broker-feed, clock, calendar-coverage or runtime evidence.
