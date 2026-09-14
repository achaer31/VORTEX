// One-shot private discovery only. No orders, login, network, or permission changes.
#property strict
#property version "1.00"
#property script_show_inputs
#property description "DEMO-only macro candidate/calendar discovery; never grants context validity."

input bool EnableContextProbe = false;
input long ExpectedDemoLogin = 0; // Enter locally; never exported or printed.

const int CP_MAX_SYMBOLS=10000, CP_MAX_CANDIDATES=100, CP_MAX_CALENDAR_ROWS=10000;
const ulong CP_SCAN_BUDGET_MS=60000;
int cp_lock=INVALID_HANDLE,cp_file=INVALID_HANDLE;
string cp_folder="";
bool cp_disk_failed=false,cp_scan_complete=false,cp_calendar_complete=false;
int cp_total=0,cp_seen=0,cp_candidates=0,cp_symbol_errors=0;
int cp_query_returned=0,cp_query_error=0,cp_value_rows=0,cp_examined=0;
int cp_low=0,cp_moderate=0,cp_high=0,cp_none=0,cp_metadata_errors=0,cp_ambiguous_high=0;
int cp_unknown_importance=0,cp_outside_window=0;
datetime cp_started=0,cp_received=0,cp_server=0,cp_server_host_sample=0,cp_last_quote=0,cp_from=0,cp_to=0;
ulong cp_start_ms=0,cp_end_ms=0,cp_sequence=0;

string CpInteger(const long value) { return StringFormat("%I64d",value); }
string CpNumber(const double value) { return DoubleToString(value,16); }
string CpStamp(const datetime value)
{
   string text=TimeToString(value,TIME_DATE|TIME_SECONDS);
   StringReplace(text,".","-"); StringReplace(text," ","T");
   return text; // No Z suffix: host accuracy and server UTC offset are unverified.
}
void CpCell(string &row,string value)
{
   StringReplace(value,"\"","\"\"");
   if(row!="") row+=",";
   row+="\""+value+"\"";
}
bool CpWrite(const int handle,const string line)
{
   uchar bytes[]; ResetLastError();
   int count=StringToCharArray(line+"\r\n",bytes,0,WHOLE_ARRAY,CP_UTF8);
   if(handle==INVALID_HANDLE || count<=1 || GetLastError()!=0)
   { cp_disk_failed=true; return false; }
   ResetLastError();
   uint written=FileWriteArray(handle,bytes,0,(uint)(count-1));
   if(written!=(uint)(count-1) || GetLastError()!=0)
   { cp_disk_failed=true; return false; }
   ResetLastError(); FileFlush(handle);
   if(GetLastError()!=0) { cp_disk_failed=true; return false; }
   return true;
}
bool CpIdentity(string &reason)
{
   ResetLastError();
   long login=AccountInfoInteger(ACCOUNT_LOGIN);
   long mode=AccountInfoInteger(ACCOUNT_TRADE_MODE);
   long margin=AccountInfoInteger(ACCOUNT_MARGIN_MODE);
   string currency=AccountInfoString(ACCOUNT_CURRENCY);
   bool connected=(bool)TerminalInfoInteger(TERMINAL_CONNECTED);
   long login_after=AccountInfoInteger(ACCOUNT_LOGIN);
   if(GetLastError()!=0) { reason="identity_read_failed"; return false; }
   if(ExpectedDemoLogin<=0 || login!=ExpectedDemoLogin || login_after!=ExpectedDemoLogin)
   { reason="account_mismatch"; return false; }
   if(mode!=ACCOUNT_TRADE_MODE_DEMO) { reason="demo_required"; return false; }
   if(currency!="USD" || margin!=ACCOUNT_MARGIN_MODE_RETAIL_HEDGING)
   { reason="usd_hedging_required"; return false; }
   if(!connected) { reason="terminal_disconnected"; return false; }
   return true;
}
bool CpContinue(string &reason)
{
   if(IsStopped()) { reason="interrupted"; return false; }
   return CpIdentity(reason);
}
bool CpProperty(const string category,const string symbol,const string field,
                const string value,const bool available,const int error,string &reason)
{
   if(!CpContinue(reason)) return false;
   string row="";
   CpCell(row,CpInteger((long)++cp_sequence)); CpCell(row,CpStamp(TimeGMT()));
   CpCell(row,CpInteger((long)GetTickCount64())); CpCell(row,category); CpCell(row,symbol);
   CpCell(row,field); CpCell(row,available?value:"");
   CpCell(row,available?"REPORTED_UNREVIEWED":"UNAVAILABLE"); CpCell(row,CpInteger(error));
   CpCell(row,"candidate_label_only_not_valid_macro"); CpCell(row,"host_UTC_unverified");
   if(!CpWrite(cp_file,row)) { reason="disk_write_failed"; return false; }
   return true;
}
bool CpReadString(const string symbol,const ENUM_SYMBOL_INFO_STRING field,string &value,
                  bool &available,int &error,string &reason)
{
   if(!CpContinue(reason)) return false;
   ResetLastError(); bool ok=SymbolInfoString(symbol,field,value); error=GetLastError();
   if(!CpContinue(reason)) return false;
   available=ok && error==0 && StringLen(value)>0;
   if(!available) { ++cp_symbol_errors; value=""; }
   return true;
}
bool CpStringProperty(const string category,const string symbol,const string key,
                      const ENUM_SYMBOL_INFO_STRING field,string &reason)
{
   string value=""; bool available=false; int error=0;
   if(!CpReadString(symbol,field,value,available,error,reason)) return false;
   return CpProperty(category,symbol,key,value,available,error,reason);
}
bool CpIntegerProperty(const string category,const string symbol,const string key,
                       const ENUM_SYMBOL_INFO_INTEGER field,string &reason)
{
   if(!CpContinue(reason)) return false;
   long value=0; ResetLastError(); bool ok=SymbolInfoInteger(symbol,field,value); int error=GetLastError();
   if(!CpContinue(reason)) return false;
   bool available=ok && error==0;
   if(!available) ++cp_symbol_errors;
   return CpProperty(category,symbol,key,CpInteger(value),available,error,reason);
}
bool CpDoubleProperty(const string category,const string symbol,const string key,
                      const ENUM_SYMBOL_INFO_DOUBLE field,string &reason)
{
   if(!CpContinue(reason)) return false;
   double value=0; ResetLastError(); bool ok=SymbolInfoDouble(symbol,field,value); int error=GetLastError();
   if(!CpContinue(reason)) return false;
   bool available=ok && error==0 && MathIsValidNumber(value) && value!=EMPTY_VALUE;
   if(!available) ++cp_symbol_errors;
   return CpProperty(category,symbol,key,CpNumber(value),available,error,reason);
}
string CpCandidate(const string symbol,const string description)
{
   string label=symbol+" "+description; StringToUpper(label);
   if(StringFind(label,"DXY")>=0 || StringFind(label,"USDX")>=0 ||
      StringFind(label,"USDIDX")>=0 || StringFind(label,"USD INDEX")>=0 ||
      StringFind(label,"DOLLAR INDEX")>=0)
      return "DOLLAR_INDEX_LABEL_CANDIDATE";
   if(StringFind(label,"US10Y")>=0 || StringFind(label,"UST10")>=0 ||
      StringFind(label,"TNX")>=0 || StringFind(label,"US 10 YEAR")>=0 ||
      StringFind(label,"US 10-YEAR")>=0 || StringFind(label,"US10YR")>=0 ||
      StringFind(label,"U.S. 10")>=0 ||
      ((StringFind(label,"10 YEAR")>=0 || StringFind(label,"10-YEAR")>=0) &&
       (StringFind(label,"TREASURY")>=0 || StringFind(label,"T-NOTE")>=0 ||
        StringFind(label,"YIELD")>=0)))
      return "TEN_YEAR_LABEL_CANDIDATE";
   return "";
}
bool CpSymbols(string &reason)
{
   if(!CpContinue(reason)) return false;
   ResetLastError(); cp_total=SymbolsTotal(false); int error=GetLastError();
   if(!CpContinue(reason)) return false;
   if(error!=0 || cp_total<=0 || cp_total>CP_MAX_SYMBOLS)
   { reason="symbol_catalog_unavailable_or_limit"; return false; }
   string seen[];
   for(int i=0;i<cp_total;++i)
   {
      if(!CpContinue(reason)) return false;
      if(GetTickCount64()-cp_start_ms>CP_SCAN_BUDGET_MS)
      { reason="symbol_scan_budget_exceeded"; return false; }
      ResetLastError(); string symbol=SymbolName(i,false); error=GetLastError();
      if(!CpContinue(reason)) return false;
      if(error!=0 || symbol=="") { reason="symbol_name_unavailable"; return false; }
      for(int j=0;j<ArraySize(seen);++j)
         if(seen[j]==symbol) { reason="symbol_catalog_changed"; return false; }
      if(ArrayResize(seen,i+1,256)!=i+1) { reason="allocation_failed"; return false; }
      seen[i]=symbol; ++cp_seen;
      string description=""; bool available=false;
      if(!CpReadString(symbol,SYMBOL_DESCRIPTION,description,available,error,reason)) return false;
      string category=CpCandidate(symbol,description);
      if(category=="") continue;
      if(cp_candidates>=CP_MAX_CANDIDATES) { reason="candidate_limit_exceeded"; return false; }
      ++cp_candidates;
      bool ok=CpProperty(category,symbol,"name",symbol,true,0,reason) &&
         CpProperty(category,symbol,"description",description,available,error,reason) &&
         CpIntegerProperty(category,symbol,"selected",SYMBOL_SELECT,reason) &&
         CpIntegerProperty(category,symbol,"custom",SYMBOL_CUSTOM,reason) &&
         CpIntegerProperty(category,symbol,"trade_calc_mode",SYMBOL_TRADE_CALC_MODE,reason) &&
         CpIntegerProperty(category,symbol,"trade_mode",SYMBOL_TRADE_MODE,reason) &&
         CpIntegerProperty(category,symbol,"chart_mode",SYMBOL_CHART_MODE,reason) &&
         CpIntegerProperty(category,symbol,"digits",SYMBOL_DIGITS,reason) &&
         CpDoubleProperty(category,symbol,"point",SYMBOL_POINT,reason) &&
         CpDoubleProperty(category,symbol,"contract_size",SYMBOL_TRADE_CONTRACT_SIZE,reason) &&
         CpStringProperty(category,symbol,"currency_base",SYMBOL_CURRENCY_BASE,reason) &&
         CpStringProperty(category,symbol,"currency_profit",SYMBOL_CURRENCY_PROFIT,reason);
      if(!ok) return false;
   }
   ResetLastError(); int total_after=SymbolsTotal(false); error=GetLastError();
   if(!CpContinue(reason)) return false;
   if(error!=0 || total_after!=cp_total) { reason="symbol_catalog_changed"; return false; }
   cp_scan_complete=true;
   return true;
}
bool CpCalendar(string &reason)
{
   if(!CpContinue(reason)) return false;
   cp_server=TimeTradeServer(); cp_server_host_sample=TimeGMT(); cp_last_quote=TimeCurrent();
   if(cp_server<=3600 || cp_server_host_sample<=0 || cp_last_quote<=0)
   { reason="server_time_unavailable"; return false; }
   // Calendar API uses trade-server time; do not convert unverified clocks to UTC.
   cp_from=(datetime)((long)cp_server-3600); cp_to=(datetime)((long)cp_server+86400);
   MqlCalendarValue values[]; ResetLastError();
   cp_query_returned=CalendarValueHistory(values,cp_from,cp_to,NULL,"USD");
   cp_query_error=GetLastError();
   if(!CpContinue(reason)) return false;
   cp_value_rows=ArraySize(values);
   if(cp_value_rows>CP_MAX_CALENDAR_ROWS) { reason="calendar_row_limit"; return false; }
   for(int i=0;i<cp_value_rows;++i)
   {
      if(!CpContinue(reason)) return false;
      MqlCalendarEvent event; ResetLastError();
      bool ok=CalendarEventById(values[i].event_id,event); int error=GetLastError();
      if(!CpContinue(reason)) return false;
      ++cp_examined;
      if(values[i].time<cp_from || values[i].time>cp_to) ++cp_outside_window;
      if(!ok || error!=0) { ++cp_metadata_errors; continue; }
      if(event.importance==CALENDAR_IMPORTANCE_HIGH)
      {
         ++cp_high;
         if(event.time_mode!=CALENDAR_TIMEMODE_DATETIME) ++cp_ambiguous_high;
      }
      else if(event.importance==CALENDAR_IMPORTANCE_MODERATE) ++cp_moderate;
      else if(event.importance==CALENDAR_IMPORTANCE_LOW) ++cp_low;
      else if(event.importance==CALENDAR_IMPORTANCE_NONE) ++cp_none;
      else ++cp_unknown_importance;
   }
   cp_received=TimeGMT(); cp_end_ms=GetTickCount64();
   if(!CpContinue(reason)) return false;
   cp_calendar_complete=cp_query_returned>=0 && cp_query_returned==cp_value_rows &&
      cp_query_error==0 && cp_metadata_errors==0 && cp_unknown_importance==0 &&
      cp_outside_window==0 && cp_ambiguous_high==0;
   return true; // API/data failure is reported explicitly, never converted to coverage.
}
bool CpMeta(const int handle,const string key,const string value)
{
   string line=""; CpCell(line,key); CpCell(line,value);
   return CpWrite(handle,line);
}
void CpManifest(bool valid,string reason)
{
   // A final account change redacts aggregate measurements and invalidates this run.
   string identity_reason="";
   if(valid && !CpContinue(identity_reason)) { valid=false; reason=identity_reason; }
   int out=FileOpen(cp_folder+"\\manifest.csv",FILE_WRITE|FILE_BIN|FILE_SHARE_READ);
   if(out==INVALID_HANDLE) { cp_disk_failed=true; return; }
   bool clean=valid && cp_scan_complete && cp_calendar_complete && cp_symbol_errors==0;
   bool ok=CpWrite(out,"key,value");
   ok=ok && CpMeta(out,"schema","vortex.native.context-discovery.v1");
   ok=ok && CpMeta(out,"status",!valid?"INVALID":clean?"DISCOVERY_COMPLETED":"DISCOVERY_COMPLETED_WITH_ISSUES");
   ok=ok && CpMeta(out,"action","WAIT");
   ok=ok && CpMeta(out,"reason",reason);
   ok=ok && CpMeta(out,"origin","actual_terminal_probe_unreviewed");
   ok=ok && CpMeta(out,"host_started_label",CpStamp(cp_started));
   ok=ok && CpMeta(out,"host_received_label",valid?CpStamp(cp_received):"");
   ok=ok && CpMeta(out,"elapsed_monotonic_ms",valid?CpInteger((long)(cp_end_ms-cp_start_ms)):"");
   ok=ok && CpMeta(out,"server_time_label",valid?CpStamp(cp_server):"");
   ok=ok && CpMeta(out,"server_last_quote_label",valid?CpStamp(cp_last_quote):"");
   ok=ok && CpMeta(out,"paired_host_time_label",valid?CpStamp(cp_server_host_sample):"");
   ok=ok && CpMeta(out,"server_minus_host_label_seconds",valid?CpInteger((long)cp_server-(long)cp_server_host_sample):"");
   ok=ok && CpMeta(out,"utc0_clock_consistency",!valid?"UNAVAILABLE":
      MathAbs((double)((long)cp_server-(long)cp_server_host_sample))<=10.0?
      "CONSISTENT_UNVERIFIED":"DISAGREEMENT_OR_SAMPLE_DELAY");
   ok=ok && CpMeta(out,"clock_accuracy","UNVERIFIED");
   ok=ok && CpMeta(out,"server_utc_offset","UNKNOWN_NOT_INFERRED_FROM_CLOCK_DIFFERENCE");
   ok=ok && CpMeta(out,"symbol_catalog_count",valid?CpInteger(cp_total):"");
   ok=ok && CpMeta(out,"symbol_names_examined",valid?CpInteger(cp_seen):"");
   ok=ok && CpMeta(out,"candidate_count",valid?CpInteger(cp_candidates):"");
   ok=ok && CpMeta(out,"symbol_property_errors",valid?CpInteger(cp_symbol_errors):"");
   ok=ok && CpMeta(out,"symbol_scan_completed",valid && cp_scan_complete?"true":"false");
   ok=ok && CpMeta(out,"catalog_scope","all_names_available_descriptions_keyword_match_only");
   ok=ok && CpMeta(out,"calendar_currency","USD");
   ok=ok && CpMeta(out,"calendar_query_start_server",valid?CpStamp(cp_from):"");
   ok=ok && CpMeta(out,"calendar_query_end_server",valid?CpStamp(cp_to):"");
   ok=ok && CpMeta(out,"calendar_api_returned",valid?CpInteger(cp_query_returned):"");
   ok=ok && CpMeta(out,"calendar_api_error",valid?CpInteger(cp_query_error):"");
   ok=ok && CpMeta(out,"calendar_value_rows",valid?CpInteger(cp_value_rows):"");
   ok=ok && CpMeta(out,"calendar_metadata_examined",valid?CpInteger(cp_examined):"");
   ok=ok && CpMeta(out,"calendar_metadata_errors",valid?CpInteger(cp_metadata_errors):"");
   ok=ok && CpMeta(out,"calendar_high_values",valid?CpInteger(cp_high):"");
   ok=ok && CpMeta(out,"calendar_moderate_values",valid?CpInteger(cp_moderate):"");
   ok=ok && CpMeta(out,"calendar_low_values",valid?CpInteger(cp_low):"");
   ok=ok && CpMeta(out,"calendar_none_values",valid?CpInteger(cp_none):"");
   ok=ok && CpMeta(out,"calendar_unknown_importance",valid?CpInteger(cp_unknown_importance):"");
   ok=ok && CpMeta(out,"calendar_high_ambiguous_time",valid?CpInteger(cp_ambiguous_high):"");
   ok=ok && CpMeta(out,"calendar_values_outside_window",valid?CpInteger(cp_outside_window):"");
   ok=ok && CpMeta(out,"calendar_query_consistent",valid && cp_calendar_complete?"true":"false");
   ok=ok && CpMeta(out,"coverage_attested","false");
   ok=ok && CpMeta(out,"news_valid","false");
   ok=ok && CpMeta(out,"macro_valid","false");
   ok=ok && CpMeta(out,"historical_available_at_proven","false");
   ok=ok && CpMeta(out,"execution_enabled","false");
   ok=ok && CpMeta(out,"strategy_approval","false");
   // Completion is last and requires another identity check. Earlier rows remain
   // provisional if an account switch or stop happens while writing the manifest.
   bool identity_final=valid && CpContinue(identity_reason);
   ok=ok && CpMeta(out,"identity_valid_at_manifest_end",identity_final?"true":"false");
   ok=ok && CpMeta(out,"manifest_complete",ok && !cp_disk_failed && identity_final?"true":"false");
   FileClose(out);
}
void OnStart()
{
   if(!EnableContextProbe || ExpectedDemoLogin<=0)
   { Print("Context probe disabled; no account reads or files."); return; }
   if((bool)MQLInfoInteger(MQL_TESTER))
   { Print("Context probe refused in Strategy Tester."); return; }
   string reason="";
   if(!CpContinue(reason)) { Print("Context probe blocked: ",reason); return; }
   cp_lock=FileOpen("VortexContextProbe.lock",FILE_READ|FILE_WRITE|FILE_BIN);
   if(cp_lock==INVALID_HANDLE) { Print("Context probe lock unavailable."); return; }
   cp_started=TimeGMT(); cp_start_ms=GetTickCount64();
   cp_folder="VortexContextProbe_"+CpInteger((long)cp_started)+"_"+CpInteger((long)cp_start_ms);
   if(!FolderCreate(cp_folder)) { FileClose(cp_lock); Print("Context probe folder unavailable."); return; }
   cp_file=FileOpen(cp_folder+"\\candidates.csv",FILE_WRITE|FILE_BIN|FILE_SHARE_READ);
   bool ok=CpWrite(cp_file,"sequence,received_host_utc_label,receipt_monotonic_ms,category,symbol,field,value,status,api_error,scope,clock_accuracy");
   if(ok) ok=CpSymbols(reason);
   if(ok) ok=CpCalendar(reason);
   if(cp_file!=INVALID_HANDLE) FileClose(cp_file);
   if(!cp_disk_failed) CpManifest(ok,reason);
   FileClose(cp_lock);
   Print(cp_disk_failed?"Context probe disk failure; discard incomplete output.":
                       "Context discovery finished; inspect private manifest; context remains invalid. ",cp_folder);
}
