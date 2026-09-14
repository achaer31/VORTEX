# VORTEX XAU EXTREME v0.2 — frozen hypotheses

Status: BACKTEST/PAPER only; unvalidated. This specification is written before
running v0.2 on the exported market data. No parameter fitting, grid selection,
or profitable-result selection is permitted. A bug fix must be recorded and
rerun consistently. A changed hypothesis becomes v0.3 on new data.

## Clocks, data and availability

M5 completed candles produce decisions; earliest fill is next contiguous M5
open. M15, H1 and H4 context is backward-asof on completed bar CLOSE, with age
strictly less than one respective timeframe. Reject the first entry after a
missing M5 bar. EMA200 needs 200 observed bars; H4 is built only from complete
four-H1 UTC buckets. No interpolation or future HTF candles.

v0.2 interprets Exness time as UTC based on broker documentation:
https://get.exness.help/hc/en-us/articles/360014390760-What-is-the-default-timezone-set-for-MetaTrader
The historical export itself labels the offset unknown; this explicit new
assumption does not change the archived v0.1 files or certify historical DST.

Sessions: Asia 09:00–15:00 Asia/Tokyo; London 08:00–17:00 Europe/London;
New York 08:00–17:00 America/New_York, start inclusive/end exclusive. Local
timezones handle DST. Session highs/lows exclude the decision candle; current
levels grow causally and previous completed levels may carry between sessions.
London or New York (including overlap) is ideal for EXTREME. Other sessions may
qualify for NORMAL/AGGRESSIVE. Broker available bars determine market availability.

Mandatory external inputs: USD high-impact economic-calendar events AND
point-in-time coverage attestations, plus DXY and US 10-year yield observations
with observed_at and available_at. No external data means ATLAS INVALID and no
entry. Empty calendar events do NOT mean no news unless coverage is attested.
Calendar unavailable, or high-impact USD release within inclusive ±10 minutes,
blocks entry. Macro observations older than 60 minutes are stale; one previous
available observation is needed for change calculations. Revised/future data
must not leak through available_at. These feeds are currently absent.

Historical spread is the last completed bid bar's spread_points × symbol point.
Execution proxy PASS requires finite positive spread <= min(0.60 USD, 0.10×M15
ATR). This is an OHLC proxy, not measured broker latency/rejection or bid/ask tick
history. Demo additionally needs actual fresh bid/ask, connection, executable
volume and confirmed protection. Never fill missing latency with zero.

## Six deterministic modules

All directional scores clipped to [-100,100]; neutral 0 is valid only when all
required inputs exist. Missing required input produces NaN/null and INVALID.
Indicator EMA uses adjust=False with period minimum observations. ATR14/RSI14
use Wilder SMA seed then alpha=1/14; flat RSI=50. MACD=(EMA12−EMA26), signalEMA9.
All windows count observed, completed bars; freshness guards handle time gaps.

- ORION: on each M15/H1/H4, stack=100×mean(sign(close−EMA20),
  sign(EMA20−EMA50),sign(EMA50−EMA200)). Slope=clip(100×(EMA20−EMA20[5])/ATR).
  Timeframe score=.75×stack+.25×slope. ORION=.20×M15+.40×H1+.40×H4.
  HTF alignment=+1/−1 only for fully ordered bullish/bearish EMA stacks; else0.
- VORTEX: .40×clip(4×(RSI14−50))+.35×clip(400×MACD_hist/ATR_M5)
  +.25×clip(50×(close−close[3])/ATR_M5).
- NOVA: strict swing pivot with 2 left and 2 right bars, known only at the close
  of the second right bar. Last two confirmed highs/lows define HH+HL (+70) or
  LH+LL (−70). Breakout beyond the prior confirmed pivot by .05×ATR_M15 adds
  30 in the aligned structure direction; a retest within six completed M5 bars
  of that break, within .15×ATR_M15 and closing back on the breakout side,
  also adds30 (never double count). Break without aligned structure is ±50;
  other complete but unresolved structures score0.
- LUNA: sweep a prior20-bar high/low or known Asia/London/NY level by at least
  .05×ATR_M15, close back through that level, and rejection wick at least body
  size. Bullish sweep+85, bearish−85; both directions in one candle=0 conflict.
  A confirmed sweep persists for at most 3 following closed bars, decaying
  5 points per bar. No sweep=0; tick volume is not a liquidity substitute.
- KIRA: unsigned volatility state. M15 ATR / preceding50-ATR median ratio.
  Quality20 if ATR/price<.00025 or ratio<.5;50 for ratio[.5,.8);75 for
  ratio[.8,1.8) with ATR/price<=.01;90 when ratio>=1.8 or ATR/price>.01.
  Missing/zero baseline=INVALID. Quality>=85 blocks all entries as too wild.
- ATLAS: macro_direction=.60×clip(−100×DXY_change_percent/.20)
  +.40×clip(−100×US10y_change_percentage_points/.05). With complete calendar,
  fresh macro, session and execution inputs, ATLAS=macro_direction. Session,
  news and spread are explicit quality gates, not invented directional votes.

Weights requested O20/V15/N20/L20/K10/A15. KIRA has no direction: directional
mean=(.20O+.15V+.20N+.20L+.15A)/.90. Consensus=directional_mean×(.90+.10K/100).
Thus KIRA's10% is a confidence modifier, never a bullish vote or a sixth
independent strategy. Scores are heuristic units, not calibrated probabilities.

## Modes and independent risk gate

Direction comes from consensus sign. Compare each signed directional score
after multiplying by direction. NORMAL: consensus>=72, O>=70,V>=55,N>=75,
L>=55,K in[45,85), A>=−35. AGGRESSIVE additionally consensus>=78,O>=75,
N>=80,V>=65,L>=70,A>=50 and H1/H4 aligned. EXTREME additionally consensus>=82,
O>=80,V>=70,N>=80,L>=80,A>=70,K in[60,84], H1/H4 aligned and ideal session.
All five directional engines must support EXTREME plus KIRA passes; none may
be strongly contrary. Missing any mandatory input blocks every mode.

Normal2%, aggressive3.5%, extreme5% of current equity. A risk-cap sweep of
2/3.5/5/7.5% is reported in full; the7.5% cap never overrides the5% base-mode
limit. Separate fixed-risk sensitivity runs may use7.5% base, must be labeled
nondeployable, and never become the production setting by performance selection.

Stop distance=max(1.4×M15 ATR, distance beyond confirmed structural invalidation
plus .1×ATR). Minimum .35×ATR; reject if >2.2×ATR or invalid. Round the stop
outward to actual tick size. Stop anchor is known confirmed swing low for LONG,
high for SHORT. Minimum expected target RR2.0; TP2=2.5R satisfies the target
level constraint, not a guaranteed realized average RR after partial exits.

Risk gate is independent of voting. Round lots DOWN, reserve costs/margin, never
force minimum lots. Offline USD-linear contract calculator is an assumption;
demo must call broker order_calc_profit/order_calc_margin and confirm metadata.
Exact requested exits: TP1 at1.5R closes25%, TP2 at2.5R closes25%, runner50%.
Every partial and remainder must meet lot_min/lot_step. With .01 minimum/step,
base minimum is .04 lot. Reject split_lot when smaller; do not enlarge risk or
silently replace the exit plan. Runner after TP2 uses tighter of 1.3×M15 ATR
or confirmed structure, based on previous completed data, with monotonic SL.

At most one base campaign plus2 adds. Add1: previous close>=+1R, base stop
confirmed at breakeven including costs, consensus>=78 and current quote remains
profitable, fresh inputs/no news: nominal risk1.5%. Add2: >=+2R, consensus>=82,
O/N>=80 aligned, earlier legs protected and non-losing: risk1%. Each add must
also support exact partials. Max cumulative nominal risk7.5% of campaign starting
equity, max net open planned risk7.5% of current equity. Locked profits do not
offset unrelated losing risk to justify a larger add. Never martingale/average
losers. No fixed trade count or forced waiting-period optimization.

2 losing campaigns: halve new risk, EXTREME disabled.3: persistent FROZEN for
the rest of the run until explicit review/reset (not automatically next day).
Daily equity DD from day-start equity>=10% disables EXTREME, >=15% KILL exits
positions conservatively in simulation. Includes floating and costs. Gaps can
exceed planned stop/DD limits. Data/broker disconnect blocks new entry while
previous broker-side protective orders remain essential.

## Frozen research protocol and promotion gates

Initial equity$50 in each independent run. No milestone forecast: $50/$100/$250/
$500/$1000 are labels only. No rescaling returns to pretend a live equity curve.

Existing March–September2026 dataset was entirely viewed in v0.1. Report full
descriptive and non-overlapping60/20/20 day partitions (IS/validation/retrospective
OOS), explicitly NOT genuine unseen OOS. Expanding walk-forward starts60 days,
tests next20 days, advances20; fit window metadata only, parameters remain fixed,
test intervals disjoint and each starts$50 with prior causal indicator warmup.
Carry no future positions/equity between independent folds.

Costs: baseline observed prior-bar spread×1, slippage$0.03/oz/side, commission
$0/lot/side as unverified assumption; stress spread×2, slippage$0.10, commission
$3.50/lot/side as sensitivity. Swap uses current exported snapshot: long
−534.9points×.001×100=−$53.49/lot/day, short$0; Wednesday triple, weekdays only.
Stress longswap×2, short−$5/lot/day sensitivity. These are NOT historical broker
cost schedules; no certification of historical commission, financing or margin.
SL-first if intrabar stop/target both touched; gap stops fill adversely at open,
targets get their level; no favorable current-bar path inference.

Automated software tests prove mechanics only. Promotion to forward DEMO requires:
all safety tests passing, complete point-in-time inputs and broker metadata/costs,
genuine unseen evaluation after model freeze, at least100 closed campaigns over
at least60 trading days, positive net OOS expectancy with block-bootstrap95%
lower bound>0, baseline PF>1.2, stressed PF>1, no planned-risk/ownership failures,
max equity DD<=15%, and positive net results in at least two-thirds of unseen
walk-forward test windows. These are minimum review criteria, not statistical
proof or profit guarantees. Missing metrics => NOT_EVALUABLE, never PASS.
v0.2 has no codepath that promotes itself or enables broker trading.
