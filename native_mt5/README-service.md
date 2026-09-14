# Read-only MT5 observation service

`VortexNativeObserveService.mq5` hosts the existing observer as an MT5 service.
It includes the unchanged observer and signal core rather than duplicating their
calculation or journal logic. No risk planner, order adapter or LLM is invoked.
See the [target verification](validation-service-2026-09-14.json) for the exact
source, compiler and captured journal evidence.

Compile the service with `VortexNativeObserve.mq5` and `VortexSignalCore.mqh` in
the same source directory. Install its compiled binary under `MQL5/Services`.
Refresh Navigator, choose Add Service, configure the expected DEMO login privately
and enable observation. Leave Allow Algo Trading unchecked. The default settings
do nothing. The service waits for the expected connected USD hedging DEMO account
before entering the observer. It does not authenticate or switch accounts.

Only one observer may run in this terminal data directory: the service and chart
script use the same exclusive file lock. Stop the old observation script before
starting the service; preserve its journal. The separate evidence collector has
its own lock and may continue. A lock or disk failure ends that service attempt
instead of repeatedly creating journals and concealing the failure.

Once started, the reused observer records health about every five seconds and
calculates a new decision when a closed M5 bar is available. Missing mandatory
context stays FROZEN/WAIT. Between decisions, score fields are blank. Connection,
identity, stale quote, history and disk failure behavior is inherited from the
observer. Its initial late bootstrap observation is not an executable entry.

[MetaQuotes documents](https://www.mql5.com/en/docs/runtime/running) services as
independent of charts and describes reloading running services when the terminal
starts again. That does not establish Windows login, terminal startup after a VPS
reboot, crash recovery, broker reconciliation, order protection or a watchdog.
The service's terminal-start behavior still requires a separate acceptance test.

This deployment verifies an interval of market observation after the old chart
observer was stopped. The original chart was subsequently closed while the
service continued writing. Other charts and the collector remained open; neither
MT5 nor Windows was restarted. Mac shutdown, Astra closure, position management,
alerts and end-to-end autonomous trading were not exercised. Status remains
**AUTONOMOUS NOT_READY**, with no strategy GO or order activation.
