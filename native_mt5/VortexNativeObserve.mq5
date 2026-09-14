// Native six-engine observation. No order adapter or permission changes.
#property strict
#property script_show_inputs
#property version "1.00"
#property description "DEMO native signal observation; no order submission."
#include "VortexSignalCore.mqh"

input bool EnableObservation=false;
input long ExpectedDemoLogin=0;
const int OBS_M5=600, OBS_M15=600, OBS_H1=1000;
int obs_lock=INVALID_HANDLE,obs_file=INVALID_HANDLE;
bool obs_disk_failed=false;
ulong obs_sequence=0,obs_tick_progress=0;
long obs_last_tick=0;
datetime obs_last_decision=0;

bool ObsFinite(double value) { return MathIsValidNumber(value) && value!=EMPTY_VALUE; }
string ObsN(double value) { return ObsFinite(value)?DoubleToString(value,16):""; }
string ObsI(long value) { return StringFormat("%I64d",value); }
string ObsB(bool value) { return value?"true":"false"; }
void ObsCell(string &row,string value)
{
   StringReplace(value,"\"","\"\"");
   if(row!="") row+=",";
   row+="\""+value+"\"";
}
bool ObsWrite(string line)
{
   uchar bytes[]; ResetLastError();
   int n=StringToCharArray(line+"\r\n",bytes,0,WHOLE_ARRAY,CP_UTF8);
   if(n<=1 || GetLastError()!=0 || obs_file==INVALID_HANDLE)
   { obs_disk_failed=true; return false; }
   ResetLastError(); uint count=FileWriteArray(obs_file,bytes,0,n-1);
   if(count!=(uint)(n-1) || GetLastError()!=0) { obs_disk_failed=true; return false; }
   ResetLastError(); FileFlush(obs_file);
   if(GetLastError()!=0) { obs_disk_failed=true; return false; }
   return true;
}
bool ObsIdentity(string &reason)
{
   ResetLastError();
   bool ok=ExpectedDemoLogin>0 && !MQLInfoInteger(MQL_TESTER) &&
      AccountInfoInteger(ACCOUNT_LOGIN)==ExpectedDemoLogin &&
      AccountInfoInteger(ACCOUNT_TRADE_MODE)==ACCOUNT_TRADE_MODE_DEMO &&
      AccountInfoInteger(ACCOUNT_MARGIN_MODE)==ACCOUNT_MARGIN_MODE_RETAIL_HEDGING &&
      AccountInfoString(ACCOUNT_CURRENCY)=="USD" &&
      TerminalInfoInteger(TERMINAL_CONNECTED) &&
      AccountInfoInteger(ACCOUNT_LOGIN)==ExpectedDemoLogin;
   if(!ok || GetLastError()!=0) { reason="identity_or_connection_invalid"; return false; }
   return true;
}
bool ObsQuote(MqlTick &tick,string &reason)
{
   double point=0; ResetLastError();
   if(!SymbolInfoTick("XAUUSD",tick) || GetLastError()!=0 ||
      !ObsFinite(tick.bid) || !ObsFinite(tick.ask) || tick.bid<=0 || tick.ask<tick.bid ||
      tick.time<=0 || tick.time_msc<=0 || tick.time_msc/1000!=(long)tick.time)
   { reason="quote_invalid"; return false; }
   if(!SymbolInfoDouble("XAUUSD",SYMBOL_POINT,point) || !ObsFinite(point) || MathAbs(point-.001)>1e-12)
   { reason="frozen_symbol_point_mismatch"; return false; }
   long age=(long)TimeTradeServer()-(long)tick.time;
   if(obs_last_tick>0 && tick.time_msc<obs_last_tick)
   { reason="tick_time_regression"; return false; }
   if(tick.time_msc!=obs_last_tick)
   { obs_last_tick=tick.time_msc; obs_tick_progress=GetTickCount64(); }
   if(age<0 || age>10 || GetTickCount64()-obs_tick_progress>10000)
   { reason="quote_stale"; return false; }
   // This is a consistency check, not an independent UTC attestation.
   if(MathAbs((double)((long)TimeTradeServer()-(long)TimeGMT()))>10)
   { reason="server_utc0_assumption_disagrees"; return false; }
   return true;
}
bool ObsRates(ENUM_TIMEFRAMES tf,int required,datetime cutoff,MqlRates &rates[],string &reason)
{
   ArraySetAsSeries(rates,false); ResetLastError();
   int n=CopyRates("XAUUSD",tf,1,required,rates);
   int error=GetLastError(); long synchronized=0;
   if(n!=required || n!=ArraySize(rates) || error!=0 ||
      !SeriesInfoInteger("XAUUSD",tf,SERIES_SYNCHRONIZED,synchronized) || synchronized==0)
   { reason=EnumToString(tf)+"_history_unavailable"; return false; }
   int seconds=PeriodSeconds(tf);
   for(int i=0;i<n;i++)
   {
      if(rates[i].time<=0 || (long)rates[i].time%seconds!=0 ||
         (i>0 && rates[i].time<=rates[i-1].time) || rates[i].time+seconds>cutoff)
      { reason=EnumToString(tf)+"_bar_time_invalid"; return false; }
   }
   return true;
}
bool ObsRecord(string kind,string reason,bool signal_available,const VxSignal &s)
{
   if(IsStopped()) return false;
   bool requested_decision=signal_available;
   string identity_reason="";
   if(signal_available && !ObsIdentity(identity_reason))
   { signal_available=false; kind="HEALTH"; reason=identity_reason; }
   string row="";
   ObsCell(row,ObsI((long)++obs_sequence)); ObsCell(row,kind); ObsCell(row,reason);
   ObsCell(row,ObsI((long)TimeGMT())); ObsCell(row,ObsI((long)GetTickCount64()));
   ObsCell(row,signal_available?ObsI((long)s.decisionTime):"");
   ObsCell(row,"READ_ONLY_NATIVE_OBSERVER"); ObsCell(row,"FROZEN"); ObsCell(row,"WAIT");
   ObsCell(row,"false"); // No execution adapter is present.
   ObsCell(row,signal_available?ObsN(s.orion):""); ObsCell(row,signal_available?s.orionReason:"");
   ObsCell(row,signal_available?ObsN(s.vortex):""); ObsCell(row,signal_available?s.vortexReason:"");
   ObsCell(row,signal_available?ObsN(s.nova):""); ObsCell(row,signal_available?s.novaReason:"");
   ObsCell(row,signal_available?ObsN(s.luna):""); ObsCell(row,signal_available?s.lunaReason:"");
   ObsCell(row,signal_available?ObsN(s.kira):""); ObsCell(row,signal_available?s.kiraReason:"");
   ObsCell(row,signal_available?ObsN(s.atlas):""); ObsCell(row,signal_available?s.atlasReason:"");
   ObsCell(row,signal_available?ObsN(s.consensus):""); ObsCell(row,signal_available?ObsN(s.atr):"");
   ObsCell(row,signal_available?ObsB(s.m15Fresh):"");
   ObsCell(row,signal_available?ObsB(s.h1Fresh):""); ObsCell(row,signal_available?ObsB(s.h4Fresh):"");
   ObsCell(row,signal_available?ObsB(s.executionValid):"");
   ObsCell(row,"calendar_macro_session_adapter_unavailable");
   ObsCell(row,"host_utc_unverified_server_utc0_assumption");
   bool written=ObsWrite(row);
   return written && (!requested_decision || signal_available);
}
void OnStart()
{
   if(!EnableObservation || ExpectedDemoLogin<=0)
   { Print("Native observation disabled; no account reads or files."); return; }
   string reason="";
   if(!ObsIdentity(reason)) { Print("Native observation blocked: ",reason); return; }
   obs_lock=FileOpen("VortexNativeObserve.lock",FILE_READ|FILE_WRITE|FILE_BIN);
   if(obs_lock==INVALID_HANDLE) { Print("Native observer lock unavailable."); return; }
   string folder="VortexNativeObserve_"+ObsI((long)TimeGMT())+"_"+ObsI((long)GetTickCount64());
   if(!FolderCreate(folder)) { FileClose(obs_lock); return; }
   obs_file=FileOpen(folder+"\\decisions.csv",FILE_WRITE|FILE_BIN|FILE_SHARE_READ);
   if(!ObsWrite("sequence,kind,reason,host_utc_epoch_label,receipt_monotonic_ms,decision_epoch_server,scope,mode,action,execution_enabled,orion,orion_reason,vortex,vortex_reason,nova,nova_reason,luna,luna_reason,kira,kira_reason,atlas,atlas_reason,consensus,atr,m15_fresh,h1_fresh,h4_fresh,historical_spread_valid,mandatory_external_state,time_basis"))
   { if(obs_file!=INVALID_HANDLE) FileClose(obs_file); FileClose(obs_lock); Print("Native observer file initialization failed."); return; }
   Print("Native signal observer started; no order adapter; private folder ",folder);
   while(!IsStopped() && !obs_disk_failed)
   {
      ulong started=GetTickCount64();
      MqlTick tick={}; VxSignal unused;
      bool healthy=ObsIdentity(reason) && ObsQuote(tick,reason);
      datetime target=(datetime)(((long)tick.time/300)*300);
      if(!healthy) ObsRecord("HEALTH",reason,false,unused);
      else if(target==obs_last_decision)
         ObsRecord("HEALTH","waiting_next_closed_m5",false,unused);
      else
      {
         MqlRates m5[],m15[],h1[]; VxExternal external[]; VxSignal rows[];
         // No external adapter: an EMPTY context is passed, never invented scores.
         ArrayResize(external,0);
         bool loaded=ObsRates(PERIOD_M5,OBS_M5,tick.time,m5,reason) &&
            ObsRates(PERIOD_M15,OBS_M15,tick.time,m15,reason) &&
            ObsRates(PERIOD_H1,OBS_H1,tick.time,h1,reason);
         if(loaded) loaded=ObsIdentity(reason) && ObsQuote(tick,reason);
         if(loaded) loaded=VxBuildSignals(m5,m15,h1,external,rows,reason);
         if(loaded) loaded=ObsIdentity(reason) && ObsQuote(tick,reason);
         int n=ArraySize(rows);
         if(loaded && n>0 && rows[n-1].decisionTime==target && target==(datetime)(((long)tick.time/300)*300) &&
            !rows[n-1].ready && rows[n-1].signal==0 && rows[n-1].mode=="FROZEN")
         {
            if(ObsRecord("DECISION","mandatory_external_inputs_unavailable",true,rows[n-1]))
               obs_last_decision=target;
         }
         else ObsRecord("HEALTH",loaded?"unexpected_or_stale_kernel_output":reason,false,unused);
      }
      while(!IsStopped() && GetTickCount64()-started<5000) Sleep(100);
   }
   if(obs_file!=INVALID_HANDLE) FileClose(obs_file);
   if(obs_lock!=INVALID_HANDLE) FileClose(obs_lock);
   Print("Native observer stopped; no unattended restart guarantee.");
}
