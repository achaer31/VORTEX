import unittest
from vortex_v02.statistics import campaign_metrics
class StatisticsTests(unittest.TestCase):
    def test_empty_is_not_performance(self):
        m=campaign_metrics([])
        self.assertIsNone(m['expectancy']);self.assertFalse(m['sufficient_sample'])
    def test_small_sample_has_no_confidence_claim(self):
        self.assertIsNone(campaign_metrics([1]*99,60)['expectancy_ci95'])
    def test_block_bootstrap_reproducible_and_losses_negative(self):
        x=[-2,-1]*50
        a=campaign_metrics(x,60,samples=100)
        self.assertEqual(a,campaign_metrics(x,60,samples=100))
        self.assertLess(a['expectancy_ci95'][1],0)
