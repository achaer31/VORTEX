import unittest
from vortex_v02.risk import BrokerSpec, Costs, exact_parts, mode_gate, size_order

class RiskTests(unittest.TestCase):
    def test_fifty_dollar_minimum_lot_blocks(self):
        p = size_order(50, .05, 4000, 3980, 1)
        self.assertEqual(p['reason'], 'min_lot')
    def test_adaptive_exit_keeps_executable_lot_without_roundup(self):
        self.assertIsNone(exact_parts(.01, BrokerSpec()))
        self.assertEqual(exact_parts(.04, BrokerSpec()), (.01,.01,.02))
        p=size_order(50,.075,4000,3999,1)
        self.assertEqual(p['exit_policy'],'single_trailing')
        self.assertEqual(p['lots'],.03)
        self.assertEqual(p['parts'],(0,0,.03))
    def test_ten_percent_is_explicit_offline_stress_only(self):
        self.assertFalse(size_order(50,.10,4000,3999,1)['allowed'])
        p=size_order(50,.10,4000,3999,1,max_risk_fraction=.10)
        self.assertTrue(p['allowed']);self.assertLessEqual(p['risk_cash'],5.)
    def test_never_rounds_risk_up(self):
        p = size_order(10000,.02,4000,3990,1)
        self.assertTrue(p['allowed'])
        self.assertLessEqual(p['risk_cash'],200)
        self.assertAlmostEqual(sum(p['parts']),p['lots'])
    def test_cost_reservation_and_invalid_stops(self):
        a=size_order(10000,.02,4000,3990,1)
        b=size_order(10000,.02,4000,3990,1,costs=Costs(1,250))
        self.assertLess(b['lots'],a['lots'])
        self.assertEqual(size_order(50,.05,4000,4001,1)['reason'],'invalid_stop')
        self.assertEqual(size_order(50,.05,4000,3999,-1)['reason'],'invalid_stop')
    def test_fails_closed_nonfinite_and_bad_margin(self):
        self.assertFalse(size_order(float('nan'),.05,4000,3990,1)['allowed'])
        self.assertEqual(size_order(10000,.05,4000,3990,1,free_margin=0)['reason'],'margin')
    def test_drawdown_and_streak(self):
        self.assertEqual(mode_gate(50,42,0,'NORMAL')[0],'KILL')
        self.assertEqual(mode_gate(50,44,0,'EXTREME')[1],'extreme_disabled')
        self.assertEqual(mode_gate(50,50,2,'NORMAL')[2],.01)
        self.assertEqual(mode_gate(50,50,3,'NORMAL')[0],'FROZEN')
        self.assertEqual(mode_gate(50,50,0,'NORMAL',connected=False)[0],'FROZEN')
