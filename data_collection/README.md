# Prospective calendar and macro collection

Prepared on 2026-09-14. These tools do not provide an approved data feed or enable a
strategy. The Python adapter's 16 synthetic tests pass, including integration with
the unchanged frozen external-context loader. The exact MQL5 source was compiled
and run once in the VPS terminal: **0 errors, 0 warnings**. Independent inspection
of the private capture and adapter confirmed **REJECTED**, because the host UTC
clock was not verified. The [sanitized validation record](calendar-validation-2026-09-14.json)
contains source/raw/log hashes and the limited test result. Raw feed files and the
compile log remain private; no market fixtures are included here. Frozen research,
its source hashes, and historical reports are unchanged.

The capture reports host-UTC labels 2026-09-14 07:58:37–07:58:39, with offset input
0 and two low-impact USD events. There were no query or metadata errors. This
demonstrates that this one terminal query returned data; the UTC labels are still
unverified and no high-impact records were returned in this sample. Coverage
remains unattested, and no normalized inputs or strategy approval were created.

The current blockers are a verified calendar feed/coverage process, documented
intraday DXY and US10y yield access, and actual receipt-time records. A prospective
capture today cannot establish what was known during the historical experiment,
nor satisfy the separate unseen-data or strategy promotion requirements.

## What the frozen input contract requires

The existing [external-context loader](../research_v02/vortex_v02/data.py) accepts:

| File | Required columns | Meaning |
| --- | --- | --- |
| `news.csv` | `event_time,known_at,currency,impact,title` | USD/high releases known by the decision. The exclusion window is inclusive ±10 minutes. |
| `coverage.csv` | `start,end,known_at` | Positive evidence that the entire decision's ±10-minute event window is covered. Empty news is insufficient. |
| `macro.csv` | `observed_at,available_at,dxy,us10y_yield` | DXY spot index points and US Treasury 10-year yield in percent per annum; yield changes are percentage points, not basis points. |

All normalized timestamps include an explicit UTC offset. Macro data must be
available by the decision, observed no more than 60 minutes earlier, and contain
two actual observations to calculate change. Neither a daily value relabeled with
the current time nor a new DXY tick can make an old yield fresh.

## Primary sources and remaining access questions

| Input | Verified source capability | What remains unresolved |
| --- | --- | --- |
| Calendar | MetaQuotes offers [CalendarValueHistory](https://www.mql5.com/en/docs/calendar/calendarvaluehistory), including a USD currency filter, plus [event metadata](https://www.mql5.com/en/docs/calendar/calendareventbyid). One actual terminal query returned two low-impact records without API errors. | Host clock, feed freshness and complete query coverage remain unverified. A historical query contains no evidence of this collector's historical receipt time. |
| DXY | ICE explicitly lists the **ICE U.S. Dollar Index, DXY** among its [currency indices](https://www.ice.com/fixed-income-data-services/index-solutions/currency-indices). | No entitled provider connection, feed symbol, observation timestamp or delay has been verified for this project. An ICE-linked data vendor/feed contract needs review. Dollar-index futures and other dollar baskets are not silently substituted. |
| Intraday US10y | Cboe lists **TNX — Cboe Interest Rate 10 Year T Note** in its [index products](https://www.cboe.com/us/indices/indicesproducts/). Its [Global Indices Feed](https://www.cboe.com/data/global-indices-feed/) offers real-time index data and links to access/vendor/history options. | Actual entitlement, delivery interface, current TNX unit conversion, observation timestamps, delay, and history coverage are unverified. The adapter accepts only already documented conversion to percent per annum; it does not guess a TNX scaling factor or use bond/futures prices as yield. |
| Daily US10y | [US Treasury rates](https://home.treasury.gov/policy-issues/financing-the-government/interest-rate-statistics) use indicative closing quotations around 15:30 New York each business day. | Daily observations do not provide continuously fresh intraday context. They are not a replacement for the frozen 60-minute freshness requirement. |

Broker symbol availability remains **UNKNOWN** until actual terminal inventory and
instrument descriptions are supplied. A familiar symbol name alone does not prove
that it is the required spot index/yield, licensed for this use, or fresh. No
provider purchase, signup, credential discovery or network integration is performed
by these tools. Historical OHLC timestamps from a vendor also do not establish when
that data was received or available to this system.

## Calendar capture

`VortexCalendarSnapshot.mq5` is a manual, one-shot Script. It queries the previous
hour through the next 24 hours of USD calendar data, records all returned events,
and writes `manifest.csv` plus `events.csv` to a new `MQL5/Files/VortexCalendar_*`
folder. It does not read account identity, place orders, alter chart symbols or
change trading settings. Local files and terminal log messages are its side effects.

Compile it with the target terminal's MetaEditor before use. Set
`ServerUtcOffsetMinutes` only after verifying the offset across the entire query
window. The default sentinel refuses capture. Calendar times and query parameters
use [trade-server time](https://www.mql5.com/en/docs/calendar/calendarvaluehistory).
Do not infer a historical offset from today's offset. Verify the host UTC clock
before setting `HostUtcClockVerified=true`; [TimeGMT](https://www.mql5.com/en/docs/dateandtime/timegmt)
depends on the computer clock and timezone configuration. The script cannot
independently attest clock accuracy and refuses Strategy Tester capture.

`received_at_utc` is recorded after the query **and all event metadata lookups**.
It is the earliest `known_at` this snapshot can provide, including events scheduled
in the past. Query errors, partial arrays, missing metadata, disconnected terminal
and high-impact events without exact times prevent usable normalization. Always
retain the immutable raw files and query logs privately.

From the repository root, validate without writing:

```sh
python data_collection/ingest.py calendar /private/path/VortexCalendar_capture
```

A successful unreviewed snapshot returns `NEEDS_COVERAGE_REVIEW` (exit 2). It can
produce a header-only coverage file, so the frozen loader keeps news invalid. To
save normalized files in a **new** private directory, add
`--output data/calendar-normalized-capture`. Do not put raw captures or completed
review documents beside these source files; `data/` is ignored by git.

`coverage.template.json` is deliberately `NOT_REVIEWED`. If actual evidence supports
coverage, a qualified operator can fill a private copy with both raw SHA-256 hashes,
the review time and specific clock/offset/feed/scope evidence, then supply
`--attestation /private/path/coverage-review.json`. Do not flip flags to make tests
or a strategy pass. The hashes prove byte consistency; flags and an evidence note
are operator assertions, not cryptographic proof that the feed was complete.

Coverage never becomes known before either capture or review. The adapter permits
a maximum **five-minute lease from capture**, with ±10-minute boundaries encoded
for the existing loader. A query covering tomorrow cannot validate decisions all
day; an expired review requires a new capture. This is a conservative acquisition
policy, not a guarantee against a new release or revision arriving between polls.
The current script has no scheduler or automated feed-health attestation.

Keep each snapshot separate. The frozen news schema has no cancellation/revision
identity: blindly concatenating calendar snapshots can leave rescheduled events in
the dataset. A future reviewed point-in-time revision adapter is required before
merging a stream. Never silently erase events that were known at an earlier decision.

## Macro ingestion

`macro.template.json` is deliberately `NOT_CONFIGURED`, has no provider credentials,
and contains no market samples. `ingest.py macro /private/path/capture.json` validates
an actual collector's already normalized packet; it does not download data.
Optional `--output data/macro-normalized-capture` creates a new output directory.

Each `samples` item must contain exactly `dxy` and `us10y_yield`. Each component
contains exactly `observed_at`, `received_at`, and numeric `value`. Observed time
comes from the verified provider's market observation, and received time from the
collector's actual UTC receipt log. Preserve underlying vendor messages privately.
Do not assign historical observations an earlier invented receipt time or assign
receipt time to an old observation. The source objects identify the provider,
verified feed symbol, documented unit conversion and entitlement; no secrets belong
in this packet.

The adapter constructs `available_at = max(component receipt times)` and
`observed_at = min(component observation times)`. This deliberately treats the pair
as only as fresh as its older member. It rejects reversed/future observation order,
nonfinite values, duplicate observations used to manufacture change history,
unreviewed instrument/unit mappings and pairs already over 60 minutes old on
receipt. Same-time value revisions require a separate revision-aware adapter.
Staleness at a later decision remains the frozen loader's responsibility.

`VALIDATED_FOR_REVIEW` means structural and chronology checks passed. It is not
proof of provider authenticity, historical completeness, acceptable strategy
performance, DEMO readiness or permission to place orders. `strategy_approval`
always remains false. The live collector is not wired to these inputs by this
package; integrating a verified provider stream is a separate bounded change.

## Checks

```sh
python -m unittest discover -s data_collection/tests -v
```

Tests create explicitly synthetic data in temporary directories and exercise
negative paths. They do not count as actual acquisition or readiness evidence.
