"""Service host contracts; not a VPS reboot/autonomy acceptance test."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).parents[1]
SERVICE = (ROOT / 'VortexNativeObserveService.mq5').read_text()
OBSERVER = (ROOT / 'VortexNativeObserve.mq5').read_text()


class NativeServiceContract(unittest.TestCase):
    def test_reuses_verified_observer_and_exclusive_lock(self):
        self.assertIn('#property service', SERVICE)
        self.assertIn('#define OnStart VxRunReadOnlyObserver', SERVICE)
        self.assertIn('#include "VortexNativeObserve.mq5"', SERVICE)
        self.assertIn('#undef OnStart', SERVICE)
        self.assertIn('VortexNativeObserve.lock', OBSERVER)
        self.assertEqual(SERVICE.count('VxRunReadOnlyObserver();'), 1)

    def test_disabled_configuration_precedes_wait_and_identity_reads(self):
        guard = SERVICE.index('if(!EnableObservation || ExpectedDemoLogin<=0)')
        self.assertLess(guard, SERVICE.index('while(!IsStopped())'))
        self.assertLess(guard, SERVICE.index('ObsIdentity(reason)'))
        self.assertRegex(SERVICE[guard:], r'disabled\."\); return;')

    def test_startup_disconnection_retries_but_failed_journal_does_not(self):
        self.assertIn('while(!IsStopped())', SERVICE)
        self.assertIn('Sleep(1000)', SERVICE)
        self.assertRegex(SERVICE, r'VxRunReadOnlyObserver\(\);\s*return;')
        self.assertIn('while(!IsStopped() && !obs_disk_failed)', OBSERVER)

    def test_no_broker_mutation_network_permission_or_restart_calls(self):
        code = re.sub(r'//[^\n]*', '', SERVICE + '\n' + OBSERVER)
        for forbidden in (r'\bOrderSend\w*\s*\(', r'\bMqlTradeRequest\b',
                          r'\bCTrade\b', r'#import', r'\bWebRequest\s*\(',
                          r'\bSocket\w*\s*\(', r'\bTerminalClose\s*\(',
                          r'\bChartSet\w*\s*\('):
            self.assertNotRegex(code, forbidden)


if __name__ == '__main__':
    unittest.main()
