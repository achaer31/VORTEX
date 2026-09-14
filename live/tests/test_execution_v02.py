"""Synthetic MT5 ledger/execution lifecycle tests. No network/terminal/orders.

Fake broker mutates only Python objects, including account switch races,
accepted-but-lost responses, broker SL/TP exits and manual-account losses.
"""
import hashlib
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from execution_v02 import Config, Decision, ExecutionStop, Manager, Store, MAGIC, REPO

NOW = 1789372800.0  # 2026-09-14 08:00 UTC, synthetic clock.
SPEC = hashlib.sha256((REPO / "research_v02/SPEC.md").read_bytes()).hexdigest()


class FakeBroker:
    ACCOUNT_TRADE_MODE_DEMO = 0
    ACCOUNT_MARGIN_MODE_RETAIL_HEDGING = 2
    SYMBOL_CHART_MODE_BID = 0
    SYMBOL_TRADE_EXECUTION_INSTANT = 1
    SYMBOL_TRADE_EXECUTION_REQUEST = 0
    SYMBOL_TRADE_MODE_FULL = 4
    ORDER_TYPE_BUY = DEAL_TYPE_BUY = 0
    ORDER_TYPE_SELL = DEAL_TYPE_SELL = 1
    DEAL_TYPE_BALANCE = 2
    DEAL_ENTRY_IN = 0
    DEAL_ENTRY_OUT = 1
    DEAL_REASON_TP = 5
    TRADE_ACTION_DEAL = 1
    TRADE_ACTION_SLTP = 6
    ORDER_TIME_GTC = 0
    ORDER_FILLING_FOK = 0
    TRADE_RETCODE_DONE = 10009

    def __init__(self):
        self.now = NOW
        self.a = NS(login=123, trade_mode=0, currency="USD", margin_mode=2,
                    balance=50., equity=50., margin_free=50., margin=0., trade_allowed=True, trade_expert=True)
        self.t = NS(connected=True, trade_allowed=True, tradeapi_disabled=False)
        self.info = NS(name="XAUUSD", chart_mode=0, trade_exemode=1, order_mode=49,
                       point=.001, trade_tick_size=.001, trade_contract_size=100., volume_min=.01,
                       volume_step=.01, volume_max=200., trade_stops_level=0, trade_freeze_level=0, trade_mode=4)
        self.tick = NS(bid=4000., ask=4000.01, time=self.now)
        self.positions, self.orders, self.sent = [], [], []
        self.deals = [NS(ticket=1, position_id=0, time=NOW-3600, type=2, entry=0, volume=0.,
                         profit=50., commission=0., swap=0., fee=0., symbol="", magic=0, reason=0)]
        self.next_ticket = 10
        self.on_check = None; self.result_mode = "done"; self.profit_unknown = False; self.margin_unknown = False

    def account_info(self): return self.a
    def terminal_info(self): return self.t
    def symbol_info(self, symbol): return self.info
    def symbol_info_tick(self, symbol): return self.tick
    def positions_get(self): return self.positions
    def orders_get(self): return self.orders

    def history_deals_get(self, *args, position=None):
        if self.deals is None: return None
        if position is not None: return [d for d in self.deals if d.position_id == position]
        return list(self.deals)

    def order_calc_profit(self, side, symbol, lots, entry, exit_price):
        if self.profit_unknown: return None
        return (exit_price-entry) * (1 if side == 0 else -1) * lots * 100

    def order_calc_margin(self, side, symbol, lots, entry):
        if self.margin_unknown: return None
        return lots * 100 * entry / 2000

    def order_check(self, request):
        if self.on_check:
            callback, self.on_check = self.on_check, None
            callback()
        return NS(retcode=0)

    def order_send(self, request):
        self.sent.append(dict(request))
        if self.result_mode == "none_no_fill": return None
        if request["action"] == self.TRADE_ACTION_SLTP:
            p = next(p for p in self.positions if p.ticket == request["position"])
            p.sl, p.tp = request["sl"], request["tp"]
        elif "position" in request:
            self.close(next(p for p in self.positions if p.ticket == request["position"]), price=request["price"])
        else:
            ticket = self.next_ticket; self.next_ticket += 1
            volume = request["volume"] / 2 if self.result_mode == "partial" else request["volume"]
            p = NS(ticket=ticket, identifier=ticket, symbol="XAUUSD", magic=request["magic"], comment=request["comment"],
                   type=request["type"], volume=volume, price_open=request["price"], price_current=request["price"],
                   sl=request["sl"], tp=request["tp"], profit=0., swap=0., time=self.now)
            self.positions.append(p)
            self.deals.append(NS(ticket=ticket*100, position_id=ticket, time=self.now, type=p.type, entry=0,
                volume=volume, profit=0., commission=0., swap=0., fee=0., symbol="XAUUSD", magic=MAGIC, reason=0))
        self.mark()
        if self.result_mode == "accepted_lost": return None
        if self.result_mode == "partial": return NS(retcode=10010)
        return NS(retcode=10009)

    def mark(self):
        for p in self.positions:
            p.price_current = self.tick.bid if p.type == 0 else self.tick.ask
            p.profit = self.order_calc_profit(p.type, p.symbol, p.volume, p.price_open, p.price_current) or 0.
        self.a.equity = self.a.balance + sum(p.profit + p.swap for p in self.positions)
        self.a.margin = sum(p.volume * 200 for p in self.positions)
        self.a.margin_free = self.a.equity - self.a.margin

    def advance(self, bid=None, seconds=300):
        self.now += seconds; self.tick.time = self.now
        if bid is not None:
            self.tick.bid, self.tick.ask = bid, bid + .01
        self.mark()

    def close(self, p, price=None, reason=0):
        price = price if price is not None else self.tick.bid if p.type == 0 else self.tick.ask
        pnl = self.order_calc_profit(p.type, p.symbol, p.volume, p.price_open, price) + p.swap
        self.deals.append(NS(ticket=self.next_ticket*100+1, position_id=p.identifier, time=self.now, type=1-p.type,
            entry=1, volume=p.volume, profit=pnl, commission=0., swap=0., fee=0., symbol=p.symbol, magic=p.magic, reason=reason))
        self.next_ticket += 1; self.positions.remove(p); self.a.balance += pnl; self.mark()

    def manual_loss(self, loss=5.72):
        self.deals.extend([
            NS(ticket=2, position_id=2, time=self.now-1800, type=0, entry=0, volume=.01, profit=0.,
               commission=0., swap=0., fee=0., symbol="XAUUSD", magic=0, reason=0),
            NS(ticket=3, position_id=2, time=self.now-900, type=1, entry=1, volume=.01, profit=-loss,
               commission=0., swap=0., fee=0., symbol="XAUUSD", magic=0, reason=0)])
        self.a.balance -= loss; self.mark()

    def manual_open(self):
        p = NS(ticket=99, identifier=99, symbol="XAUUSD", magic=0, comment="manual", type=0,
               volume=.01, price_open=self.tick.ask, price_current=self.tick.bid,
               sl=3990., tp=4010., profit=0., swap=0., time=self.now)
        self.positions.append(p)
        self.deals.append(NS(ticket=9900, position_id=99, time=self.now, type=0, entry=0,
            volume=.01, profit=0., commission=0., swap=0., fee=0., symbol="XAUUSD", magic=0, reason=0))
        self.mark(); return p


def decision(broker, atr=.5, mode="NORMAL", side=1, close=None):
    row = {name: 100. * side for name in ("orion", "vortex", "nova", "luna", "atlas")}
    row.update(kira=75., consensus=97.5*side, mode=mode, signal=side, ready=True, news_blocked=False,
               execution_valid=True, close=broker.tick.bid if close is None else close, atr=atr,
               h1_alignment=side if mode=="EXTREME" else 0, h4_alignment=side if mode=="EXTREME" else 0,
               session_ideal=mode=="EXTREME", stop_long=broker.tick.bid-1.4*atr,
               stop_short=broker.tick.ask+1.4*atr, swing_low=None, swing_high=None)
    now = broker.now // 300 * 300
    return Decision(now-300, row, {tf: now//seconds*seconds for tf, seconds in
        (("M5",300),("M15",900),("H1",3600),("H4",14400))}, SPEC)


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.api = FakeBroker()
        self.config = Config(123, NOW-86400, True, True, True)
        self.store = Store(self.tmp.name, self.config)
        self.manager = Manager(self.api, self.config, self.store, lambda: self.api.now)

    def tearDown(self):
        self.store.close(); self.tmp.cleanup()

    def restart(self):
        self.store.close(); self.store = Store(self.tmp.name, self.config)
        self.manager = Manager(self.api, self.config, self.store, lambda: self.api.now)

    def test_default_gate_never_sends(self):
        self.manager.config = Config(123, NOW-86400)
        self.assertEqual(self.manager.step(decision(self.api)), "baseline_manual_or_cost_gate_blocked")
        self.assertEqual(self.api.sent, [])

    def test_real_account_and_midcheck_switch_never_send(self):
        self.api.a.trade_mode = 2
        with self.assertRaisesRegex(ExecutionStop, "real_account"):
            self.manager.step(decision(self.api))
        self.api.a.trade_mode = 0
        self.api.on_check = lambda: setattr(self.api.a, "trade_mode", 2)
        with self.assertRaisesRegex(ExecutionStop, "real_account"):
            self.manager.step(decision(self.api))
        self.assertEqual(self.api.sent, [])

    def test_manual_loss_retains_day_anchor_and_current_sizing(self):
        self.api.manual_loss()
        self.manager.step(None)
        self.assertAlmostEqual(self.manager.state["day_start"], 50.)
        self.assertTrue(self.manager.state["extreme_disabled"])
        plan = self.manager.plan(decision(self.api), .02)
        self.assertAlmostEqual(plan["budget"], 44.28 * .02)
        with self.assertRaisesRegex(ExecutionStop, "extreme_disabled"):
            self.manager.step(decision(self.api, mode="EXTREME"))
        self.restart(); self.assertEqual(self.manager.state["day_start"], 50.)

    def test_minimum_lot_is_rejected_without_upsizing(self):
        self.api.manual_loss()
        with self.assertRaisesRegex(ExecutionStop, "min_lot"):
            self.manager.step(decision(self.api, atr=2.))
        self.assertEqual(self.api.sent, [])

    def test_unknown_history_or_missing_exposure_freezes(self):
        self.api.deals = None
        with self.assertRaisesRegex(ExecutionStop, "capital_history"):
            self.manager.step(decision(self.api))
        self.api.positions = None
        with self.assertRaisesRegex(ExecutionStop, "exposure_unknown"):
            self.manager.step(decision(self.api))

    def test_topup_or_truncated_history_rejected(self):
        extra = NS(**vars(self.api.deals[0])); extra.ticket=9; extra.profit=10.; extra.time=self.api.now-60
        self.api.deals.append(extra); self.api.a.balance=60.; self.api.mark()
        with self.assertRaisesRegex(ExecutionStop, "topup"):
            self.manager.step(None)

    def test_single_ticket_has_hard_sl_full_target(self):
        self.assertEqual(self.manager.step(decision(self.api)), "base_confirmed")
        self.assertEqual(len(self.api.positions), 1)
        p = self.api.positions[0]
        self.assertEqual(p.volume, .01); self.assertGreater(p.sl, 0)
        self.assertAlmostEqual(p.tp, round(p.price_open+2.5*(p.price_open-p.sl), 3), places=3)
        self.assertEqual(next(iter(self.manager.state["positions"].values()))["role"], "single")

    def test_partial_plan_exact_three_protected_tickets_and_real_broker_targets(self):
        self.manager.step(decision(self.api, atr=.12))
        self.assertEqual([p.volume for p in self.api.positions], [.01,.01,.02])
        self.assertTrue(all(p.sl>0 for p in self.api.positions))
        self.assertEqual(self.api.positions[-1].tp, 0)
        tp1, tp2, runner = list(self.api.positions)
        self.api.close(tp1, tp1.tp, reason=5); self.manager.step(None)
        self.assertEqual(len(self.api.positions), 2)
        self.api.close(tp2, tp2.tp, reason=5); self.manager.step(None)
        self.assertEqual(len(self.api.positions), 1)
        self.assertEqual(self.api.positions[0].identifier, runner.identifier)
        self.assertIn([0,"tp2"], self.manager.state["campaign"]["closed_roles"])

    def test_partial_fill_is_not_topped_up_even_after_restart(self):
        self.api.result_mode="partial"
        with self.assertRaisesRegex(ExecutionStop, "ambiguous"):
            self.manager.step(decision(self.api))
        self.assertEqual(len(self.api.sent), 1)
        self.restart()
        with self.assertRaisesRegex(ExecutionStop, "partial_or_unprotected"):
            self.manager.step(None)
        self.assertEqual(len(self.api.sent), 1)

    def test_accepted_lost_reply_recovers_exact_position_but_never_replays_group(self):
        self.api.result_mode="accepted_lost"
        with self.assertRaisesRegex(ExecutionStop, "ambiguous"):
            self.manager.step(decision(self.api))
        self.restart(); self.api.result_mode="done"
        self.manager.step(None)
        self.assertEqual(len(self.api.sent), 1)
        self.assertIsNone(self.manager.state["pending"])
        self.assertTrue(self.manager.state["opening"])

    def test_unfilled_unknown_intent_never_resubmits(self):
        self.api.result_mode="none_no_fill"
        with self.assertRaises(ExecutionStop): self.manager.step(decision(self.api))
        self.restart()
        with self.assertRaisesRegex(ExecutionStop, "unresolved_intent"):
            self.manager.step(None)
        self.assertEqual(len(self.api.sent), 1)

    def test_durable_intent_exists_inside_submission(self):
        original=self.api.order_send
        def send(request):
            self.assertIsNotNone(self.manager.state["pending"])
            self.assertIn(b'intent_before_send', self.store.path.read_bytes())
            return original(request)
        self.api.order_send=send
        self.manager.step(decision(self.api))

    def test_restart_duplicate_decision_does_not_add(self):
        row=decision(self.api); self.manager.step(row); count=len(self.api.sent)
        self.restart(); self.assertEqual(self.manager.step(row), "duplicate_decision")
        self.assertEqual(len(self.api.sent), count)

    def test_outage_keeps_hard_stops_then_recovers_readonly(self):
        self.manager.step(decision(self.api)); stop=self.api.positions[0].sl
        self.api.t.connected=False
        with self.assertRaisesRegex(ExecutionStop, "disconnected"): self.manager.step(None)
        self.assertEqual(self.api.positions[0].sl, stop)
        self.restart(); self.api.t.connected=True
        self.assertEqual(self.manager.step(None), "no_completed_decision")

    def test_daily_kill_closes_owned_but_never_manual_positions(self):
        self.manager.step(decision(self.api)); self.api.manual_loss(8.); manual=self.api.manual_open()
        self.assertEqual(self.manager.step(None), "daily_kill")
        self.assertEqual(self.api.positions, [manual])
        self.assertTrue(self.manager.state["daily_killed"])
        self.restart(); self.assertTrue(self.manager.state["daily_killed"])

    def test_manual_position_in_preflight_race_blocks_send(self):
        self.api.on_check=lambda:self.api.orders.append(NS(ticket=77))
        with self.assertRaisesRegex(ExecutionStop, "exposure_changed"):
            self.manager.step(decision(self.api))
        self.assertEqual(self.api.sent, [])

    def test_quote_movement_after_preflight_blocks(self):
        self.api.on_check=lambda:setattr(self.api.tick,"ask",4000.02)
        with self.assertRaisesRegex(ExecutionStop, "quote_changed"):
            self.manager.step(decision(self.api))
        self.assertEqual(self.api.sent, [])

    def test_broker_profit_or_margin_unknown_is_not_assumed(self):
        self.api.profit_unknown=True
        with self.assertRaisesRegex(ExecutionStop,"profit_unknown"): self.manager.plan(decision(self.api),.02)
        self.api.profit_unknown=False; self.api.margin_unknown=True
        with self.assertRaisesRegex(ExecutionStop,"margin_unknown"): self.manager.plan(decision(self.api),.02)

    def test_malformed_future_stale_decisions_never_send(self):
        d=decision(self.api); d.available["H4"]=self.api.now+1
        with self.assertRaisesRegex(ExecutionStop,"future_h4"): self.manager.step(d)
        self.api.advance(seconds=31)
        with self.assertRaisesRegex(ExecutionStop,"late_or_nonadjacent"): self.manager.step(decision(self.api))
        self.assertEqual(self.api.sent, [])

    def test_store_lock_and_torn_record_fail_closed(self):
        with self.assertRaisesRegex(ExecutionStop,"already_running"): Store(self.tmp.name,self.config)
        self.store.close()
        with self.store.path.open("ab") as stream: stream.write(b'{')
        with self.assertRaisesRegex(ExecutionStop,"torn"): Store(self.tmp.name,self.config)

    def test_streak_is_campaign_level_and_survives_day_change(self):
        for n in range(3):
            self.manager.step(decision(self.api,atr=.12))
            for p in list(self.api.positions): self.api.close(p,p.sl)
            self.manager.step(None); self.api.advance()
        self.assertEqual(self.manager.state["loss_streak"],3)
        self.assertTrue(self.manager.state["frozen"])
        self.api.advance(seconds=86400); self.restart(); self.manager.step(None)
        self.assertEqual(self.manager.state["loss_streak"],3)
        self.assertTrue(self.manager.state["frozen"])

    def test_actual_entry_quote_cannot_shorten_initial_atr_stop(self):
        d=decision(self.api,atr=.5)
        d.row["stop_long"]=4000.005  # Earlier structure moved close to executable fill.
        plan=self.manager.plan(d,.02)
        self.assertGreaterEqual(plan["side"]*(plan["adverse"]-plan["sl"]),.7-1e-9)

    def test_current_equity_rechecked_after_broker_preflight(self):
        # At .61 ATR, the .01 risk fits $50*2%, but cannot fit $44.28*2%.
        self.api.on_check=lambda:self.api.manual_loss()
        with self.assertRaisesRegex(ExecutionStop,"risk_changed_before_send"):
            self.manager.step(decision(self.api,atr=.61))
        self.assertEqual(self.api.sent,[])

    def test_missing_sl_uses_owned_emergency_close_even_with_manual_pending_order(self):
        self.manager.step(decision(self.api)); self.api.positions[0].sl=0
        self.api.orders.append(NS(ticket=900))
        self.assertEqual(self.manager.step(None),"unprotected_position_closed")
        self.assertEqual(self.api.positions,[])
        self.assertEqual(len(self.api.orders),1)

    def test_widened_sl_emergency_closes_only_proven_ticket(self):
        self.manager.step(decision(self.api)); self.api.positions[0].sl-=20
        self.assertEqual(self.manager.step(None),"unprotected_position_closed")
        self.assertEqual(self.api.positions,[])

    def test_broker_drops_sl_on_new_fill_immediately_emergency_closes(self):
        original=self.api.order_send
        def drop_sl(request):
            result=original(request)
            if request["action"]==1 and "position" not in request:
                self.api.positions[-1].sl=0
            return result
        self.api.order_send=drop_sl
        with self.assertRaisesRegex(ExecutionStop,"protection_failed_emergency_closed"):
            self.manager.step(decision(self.api))
        self.assertEqual(self.api.positions,[])
        self.assertEqual(len(self.api.sent),2)

    def test_sl_loss_during_protection_update_emergency_closes(self):
        self.manager.step(decision(self.api)); self.api.advance(4000.9)
        original=self.api.order_send
        def drop_sl(request):
            result=original(request)
            if request["action"]==6: self.api.positions[0].sl=0
            return result
        self.api.order_send=drop_sl
        with self.assertRaisesRegex(ExecutionStop,"protection_failed_emergency_closed"):
            self.manager.step(decision(self.api,atr=.2))
        self.assertEqual(self.api.positions,[])

    def test_multiple_missing_stops_close_each_ticket_once(self):
        self.manager.step(decision(self.api,atr=.12))
        for p in self.api.positions: p.sl=0
        self.assertEqual(self.manager.step(None),"unprotected_position_closed")
        self.assertEqual(self.api.positions,[])
        self.assertEqual(len([r for r in self.api.sent if "position" in r and r["action"]==1]),3)

    def test_actual_fill_reanchors_target_before_next_action(self):
        original=self.api.order_send
        def slipped(request):
            result=original(request)
            if request["action"]==1 and "position" not in request:
                self.api.positions[-1].price_open+=.02; self.api.mark()
            return result
        self.api.order_send=slipped
        self.manager.step(decision(self.api)); p=self.api.positions[0]
        self.assertAlmostEqual(p.tp,round(p.price_open+2.5*(p.price_open-p.sl),3),places=3)
        self.assertEqual(len([r for r in self.api.sent if r["action"]==6]),1)

    def test_manual_volume_change_cannot_be_adopted_or_emergency_closed(self):
        self.manager.step(decision(self.api)); self.api.positions[0].volume=.02
        count=len(self.api.sent)
        with self.assertRaisesRegex(ExecutionStop,"ownership_changed"): self.manager.step(None)
        self.assertEqual(len(self.api.sent),count)

    def test_winner_only_adds_maximum_two_with_confirmed_be_and_trailing(self):
        self.manager.step(decision(self.api))
        self.api.advance(4000.9)
        self.assertEqual(self.manager.step(decision(self.api,atr=.2)),"add_confirmed")
        base=[p for p in self.api.positions if self.manager.state["positions"][str(p.identifier)]["group"]==0][0]
        self.assertGreaterEqual(base.sl,base.price_open+.03-1e-8)
        self.api.advance(4001.45)
        self.assertEqual(self.manager.step(decision(self.api,atr=.2)),"add_confirmed")
        self.assertEqual(self.manager.state["campaign"]["adds"],2)
        entries=len([r for r in self.api.sent if r["action"]==1 and "position" not in r])
        self.api.advance(4001.5)
        with self.assertRaisesRegex(ExecutionStop,"add_limit"): self.manager.step(decision(self.api,atr=.2))
        self.assertEqual(len([r for r in self.api.sent if r["action"]==1 and "position" not in r]),entries)

    def test_losing_quote_forbids_add_even_when_previous_close_won(self):
        self.manager.step(decision(self.api)); self.api.advance(3999.9)
        d=decision(self.api,atr=.2,close=4001.)
        with self.assertRaisesRegex(ExecutionStop,"loser_add_forbidden"):
            self.manager.enter(d,self.api.positions)
        self.assertEqual(len(self.api.sent),1)

    def test_two_losses_halves_normal_budget_and_rejects_extreme(self):
        self.manager.step(None); self.manager.state["loss_streak"]=2; self.store.save("synthetic_two_losses")
        with self.assertRaisesRegex(ExecutionStop,"min_lot"):
            self.manager.enter(decision(self.api),[])
        with self.assertRaisesRegex(ExecutionStop,"extreme_disabled"):
            self.manager.enter(decision(self.api,mode="EXTREME"),[])

    def test_overnight_floating_anchor_is_unknown_not_reset_to_equity(self):
        self.manager.step(decision(self.api)); self.api.advance(seconds=86400)
        self.restart(); self.manager.step(None)
        self.assertIsNone(self.manager.state["day_start"])
        with self.assertRaisesRegex(ExecutionStop,"midnight_equity_unproven"):
            self.manager.enter(decision(self.api),self.api.positions)

    def test_tp2_closed_by_stop_does_not_enable_partial_runner_trail(self):
        self.manager.step(decision(self.api,atr=.12)); tp2=self.api.positions[1]
        self.api.close(tp2,tp2.sl,reason=4); self.manager.step(None)
        self.assertNotIn([0,"tp2"],self.manager.state["campaign"]["closed_roles"])


if __name__ == "__main__":
    unittest.main()
