import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import unittest
import pandas as pd
from protocol import partitions,promotion_assessment

class ProtocolTests(unittest.TestCase):
    def test_partitions_and_walkforward_have_no_future_training(self):
        p=partitions(pd.date_range('2026-01-01',periods=180,freq='D',tz='UTC'))
        parts=[p[k] for k in ('in_sample','validation','oos_previously_seen')]
        self.assertEqual(parts[0]['end'],parts[1]['start']);self.assertEqual(parts[1]['end'],parts[2]['start'])
        folds=[v for k,v in p.items() if k.startswith('walk')]
        self.assertEqual(len(folds),6)
        for fold in folds:self.assertLessEqual(fold['train_end'],fold['start'])
        for a,b in zip(folds,folds[1:]):self.assertEqual(a['end'],b['start'])
    def test_zero_or_missing_performance_can_never_promote(self):
        self.assertFalse(promotion_assessment([])['forward_demo_trading_enabled'])
