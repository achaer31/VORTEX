// Read-only service hosting the existing observer without duplicating its logic.
// Terminal service reload is not proof of Windows/VPS reboot recovery.
#property strict
#property service
#property version "1.00"
#property description "DEMO observation service; no order adapter."

#define OnStart VxRunReadOnlyObserver
#include "VortexNativeObserve.mq5"
#undef OnStart

void OnStart()
{
   // No account read, journal or loop when the operator has not configured it.
   if(!EnableObservation || ExpectedDemoLogin<=0)
   { Print("Native observation service disabled."); return; }
   bool waiting_reported=false;
   while(!IsStopped())
   {
      string reason="";
      if(ObsIdentity(reason))
      {
         // Uses the same exclusive lock, stale checks and invalid-input WAIT.
         // A disk/lock failure must not be concealed by starting another journal.
         VxRunReadOnlyObserver();
         return;
      }
      if(!waiting_reported)
      { Print("Native observation service waiting for expected DEMO connection."); waiting_reported=true; }
      Sleep(1000);
   }
}
