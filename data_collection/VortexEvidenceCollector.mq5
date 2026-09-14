// Native MT5 prospective evidence only. No orders, authentication, or network APIs.
#property strict
#property version "1.00"
#property description "Private read-only DEMO evidence; no trading or strategy decisions."
#property script_show_inputs

input bool EnableCollection = false;
input long ExpectedDemoLogin = 0; // Enter locally. Never exported or printed.

const string INSTRUMENT = "XAUUSD";
const int INTERVAL_MS = 5000;
int lock_handle = INVALID_HANDLE;
int heartbeat_handle = INVALID_HANDLE;
int spec_handle = INVALID_HANDLE;
int bar_handles[3] = {INVALID_HANDLE, INVALID_HANDLE, INVALID_HANDLE};
bool disk_failed = false;
bool anchored = false;
bool spec_written = false;
datetime next_bar[3];
long last_tick_msc = 0;
ulong last_tick_progress_ms = 0;
ulong sequence = 0;
ulong spec_attempt = 0;
string run_folder = "";

string Number(const double value) { return DoubleToString(value, 16); }
string Integer(const long value) { return StringFormat("%I64d", value); }
string Unsigned(const ulong value) { return StringFormat("%I64u", value); }
string Truth(const bool value) { return value ? "true" : "false"; }
string Stamp(const datetime value)
{
   string text = TimeToString(value, TIME_DATE | TIME_SECONDS);
   StringReplace(text, ".", "-");
   StringReplace(text, " ", "T");
   return text;
}
void Cell(string &line, const string value)
{
   string text = value;
   StringReplace(text, "\"", "\"\"");
   if(line != "") line += ",";
   line += "\"" + text + "\"";
}
bool Line(const int handle, const string line)
{
   // Binary UTF-8 permits exact byte-count checking, including short writes.
   uchar bytes[];
   int count = StringToCharArray(line + "\r\n", bytes, 0, WHOLE_ARRAY, CP_UTF8);
   if(handle == INVALID_HANDLE || count <= 1) { disk_failed = true; return false; }
   ResetLastError();
   uint written = FileWriteArray(handle, bytes, 0, (uint)(count - 1));
   if(written != (uint)(count - 1) || GetLastError() != 0)
   { disk_failed = true; return false; }
   ResetLastError();
   FileFlush(handle);
   if(GetLastError() != 0) { disk_failed = true; return false; }
   return true;
}
int NewFile(const string name)
{
   // Readers may inspect data; the collector remains its sole writer.
   int handle = FileOpen(run_folder + "\\" + name, FILE_WRITE | FILE_BIN | FILE_SHARE_READ);
   if(handle == INVALID_HANDLE) disk_failed = true;
   return handle;
}
bool Identity(string &reason)
{
   ResetLastError();
   long login = AccountInfoInteger(ACCOUNT_LOGIN);
   long mode = AccountInfoInteger(ACCOUNT_TRADE_MODE);
   string currency = AccountInfoString(ACCOUNT_CURRENCY);
   long margin_mode = AccountInfoInteger(ACCOUNT_MARGIN_MODE);
   bool connected = (bool)TerminalInfoInteger(TERMINAL_CONNECTED);
   long login_after = AccountInfoInteger(ACCOUNT_LOGIN);
   if(GetLastError() != 0)
   { reason = "identity_read_failed"; return false; }
   if(login != ExpectedDemoLogin || login_after != ExpectedDemoLogin)
   { reason = "account_mismatch"; return false; }
   if(mode != ACCOUNT_TRADE_MODE_DEMO)
   { reason = "demo_required"; return false; }
   if(currency != "USD")
   { reason = "usd_required"; return false; }
   if(margin_mode != ACCOUNT_MARGIN_MODE_RETAIL_HEDGING)
   { reason = "hedging_required"; return false; }
   if(!connected)
   { reason = "terminal_disconnected"; return false; }
   return true;
}
bool Quote(MqlTick &tick, double &point, string &reason)
{
   ResetLastError();
   if(!SymbolInfoTick(INSTRUMENT, tick) || GetLastError() != 0 ||
      !SymbolInfoDouble(INSTRUMENT, SYMBOL_POINT, point) ||
      !MathIsValidNumber(tick.bid) || !MathIsValidNumber(tick.ask) ||
      !MathIsValidNumber(point) || point <= 0 || tick.bid <= 0 || tick.ask < tick.bid ||
      tick.time <= 0 || tick.time_msc <= 0 || tick.time_msc / 1000 != (long)tick.time)
   { reason = "quote_unavailable_or_invalid"; return false; }
   long age = (long)TimeTradeServer() - (long)tick.time;
   ulong monotonic = GetTickCount64();
   if(last_tick_msc != 0 && tick.time_msc < last_tick_msc)
   { reason = "tick_time_moved_backward"; return false; }
   if(tick.time_msc != last_tick_msc)
   { last_tick_msc = tick.time_msc; last_tick_progress_ms = monotonic; }
   if(age < 0 || age > 10 || monotonic - last_tick_progress_ms > 10000)
   { reason = "quote_stale_or_clock_disagreement"; return false; }
   return true;
}
bool LoadBars(const ENUM_TIMEFRAMES tf, const int slot, const datetime cutoff,
              MqlRates &rates[], string &reason)
{
   ArrayResize(rates, 0);
   int period = PeriodSeconds(tf);
   datetime boundary = (datetime)(((long)cutoff / period) * period);
   if(next_bar[slot] >= boundary) return true;
   ArraySetAsSeries(rates, false);
   ResetLastError();
   int count = CopyRates(INSTRUMENT, tf, next_bar[slot], (datetime)((long)boundary - 1), rates);
   int error = GetLastError();
   long synced = 0;
   if(count <= 0 || count != ArraySize(rates) || error != 0 ||
      !SeriesInfoInteger(INSTRUMENT, tf, SERIES_SYNCHRONIZED, synced) || synced == 0)
   { reason = EnumToString(tf) + "_closed_data_unavailable"; return false; }
   datetime previous = 0;
   for(int i = 0; i < count; ++i)
   {
      if(rates[i].time < next_bar[slot] || rates[i].time <= previous ||
         (long)rates[i].time % period != 0 || (long)rates[i].time + period > (long)cutoff ||
         !MathIsValidNumber(rates[i].open) || !MathIsValidNumber(rates[i].high) ||
         !MathIsValidNumber(rates[i].low) || !MathIsValidNumber(rates[i].close) ||
         rates[i].low <= 0 || rates[i].low > MathMin(rates[i].open, rates[i].close) ||
         rates[i].high < MathMax(rates[i].open, rates[i].close) ||
         rates[i].tick_volume < 0 || rates[i].real_volume < 0 || rates[i].spread < 0)
      { reason = EnumToString(tf) + "_closed_data_invalid"; return false; }
      previous = rates[i].time;
   }
   return true;
}
bool SaveBars(const ENUM_TIMEFRAMES tf, const int slot, MqlRates &rates[],
              const datetime cutoff, string &reason)
{
   int period = PeriodSeconds(tf);
   for(int i = 0; i < ArraySize(rates); ++i)
   {
      if(IsStopped() || !Identity(reason)) return false;
      string line = "";
      Cell(line, "XAUUSD"); Cell(line, EnumToString(tf));
      Cell(line, Stamp(rates[i].time));
      Cell(line, Stamp((datetime)((long)rates[i].time + period)));
      Cell(line, Number(rates[i].open)); Cell(line, Number(rates[i].high));
      Cell(line, Number(rates[i].low)); Cell(line, Number(rates[i].close));
      Cell(line, Integer(rates[i].tick_volume)); Cell(line, Integer(rates[i].spread));
      Cell(line, Integer(rates[i].real_volume));
      Cell(line, Stamp(TimeGMT())); Cell(line, Unsigned(GetTickCount64()));
      Cell(line, Stamp(cutoff));
      Cell(line, Integer((long)rates[i].time - (long)next_bar[slot]));
      Cell(line, "broker_server_offset_unverified"); Cell(line, "host_UTC_unverified");
      if(!Line(bar_handles[slot], line)) { reason = "disk_write_failed"; return false; }
      // Advance only AFTER a complete flushed record. No blank bars are inserted.
      next_bar[slot] = (datetime)((long)rates[i].time + period);
   }
   return true;
}
bool SpecLine(const int handle, const string key, const string value, const string status)
{
   string line = "";
   Cell(line, Stamp(TimeGMT())); Cell(line, Unsigned(GetTickCount64()));
   Cell(line, "XAUUSD"); Cell(line, key); Cell(line, value); Cell(line, status);
   Cell(line, "current_snapshot_only"); Cell(line, "host_UTC_unverified");
   return Line(handle, line);
}
bool SpecRow(const int handle, const string key, const string value, const string status, string &reason)
{
   if(!Identity(reason)) return false;
   if(!SpecLine(handle,key,value,status)) { reason = "disk_write_failed"; return false; }
   return true;
}
bool SpecDouble(const int handle, const string key, const ENUM_SYMBOL_INFO_DOUBLE field, string &reason)
{
   double value = 0; ResetLastError();
   bool ok = SymbolInfoDouble(INSTRUMENT, field, value);
   int error = GetLastError();
   if(!Identity(reason)) return false;
   return SpecRow(handle, key, ok && error == 0 && MathIsValidNumber(value) ? Number(value) : "",
                  ok && error == 0 && MathIsValidNumber(value) ? "reported" : "unavailable", reason);
}
bool SpecInteger(const int handle, const string key, const ENUM_SYMBOL_INFO_INTEGER field, string &reason)
{
   long value = 0; ResetLastError();
   bool ok = SymbolInfoInteger(INSTRUMENT, field, value);
   int error = GetLastError();
   if(!Identity(reason)) return false;
   return SpecRow(handle, key, ok && error == 0 ? Integer(value) : "",
                  ok && error == 0 ? "reported" : "unavailable", reason);
}
bool SaveSpec(string &reason)
{
   if(!Identity(reason)) return false;
   if(spec_handle == INVALID_HANDLE)
   {
      spec_handle = NewFile("symbol-spec.csv");
      if(spec_handle == INVALID_HANDLE ||
         !Line(spec_handle, "received_host_utc_label,receipt_monotonic_ms,symbol,field,value,status,scope,clock_accuracy"))
      { reason = "disk_write_failed"; return false; }
   }
   int h = spec_handle;
   string attempt = Unsigned(++spec_attempt);
   bool ok = SpecLine(h, "capture_attempt", attempt, "STARTED");
   ok = ok && SpecInteger(h, "digits", SYMBOL_DIGITS, reason);
   ok = ok && SpecDouble(h, "point", SYMBOL_POINT, reason);
   ok = ok && SpecDouble(h, "tick_size", SYMBOL_TRADE_TICK_SIZE, reason);
   ok = ok && SpecDouble(h, "tick_value", SYMBOL_TRADE_TICK_VALUE, reason);
   ok = ok && SpecDouble(h, "tick_value_profit", SYMBOL_TRADE_TICK_VALUE_PROFIT, reason);
   ok = ok && SpecDouble(h, "tick_value_loss", SYMBOL_TRADE_TICK_VALUE_LOSS, reason);
   ok = ok && SpecDouble(h, "contract_size", SYMBOL_TRADE_CONTRACT_SIZE, reason);
   ok = ok && SpecDouble(h, "volume_min", SYMBOL_VOLUME_MIN, reason);
   ok = ok && SpecDouble(h, "volume_step", SYMBOL_VOLUME_STEP, reason);
   ok = ok && SpecDouble(h, "volume_max", SYMBOL_VOLUME_MAX, reason);
   ok = ok && SpecInteger(h, "stops_level", SYMBOL_TRADE_STOPS_LEVEL, reason);
   ok = ok && SpecInteger(h, "freeze_level", SYMBOL_TRADE_FREEZE_LEVEL, reason);
   ok = ok && SpecInteger(h, "trade_exemode", SYMBOL_TRADE_EXEMODE, reason);
   ok = ok && SpecInteger(h, "order_mode", SYMBOL_ORDER_MODE, reason);
   ok = ok && SpecInteger(h, "filling_mode", SYMBOL_FILLING_MODE, reason);
   ok = ok && SpecInteger(h, "swap_mode", SYMBOL_SWAP_MODE, reason);
   ok = ok && SpecDouble(h, "swap_long", SYMBOL_SWAP_LONG, reason);
   ok = ok && SpecDouble(h, "swap_short", SYMBOL_SWAP_SHORT, reason);
   ok = ok && SpecInteger(h, "swap_rollover3days", SYMBOL_SWAP_ROLLOVER3DAYS, reason);
   ok = ok && SpecRow(h, "commission", "", "UNKNOWN", reason);
   if(ok) ok = Identity(reason);
   // Marker rows contain no account/property values and may describe an identity failure.
   if(ok) ok = SpecLine(h, "capture_attempt", attempt, "COMPLETE");
   else if(!disk_failed) SpecLine(h, "capture_attempt", attempt, "INCOMPLETE_" + reason);
   if(disk_failed) reason = "disk_write_failed";
   return ok;
}
bool Heartbeat(bool valid, string reason, MqlTick &tick, const double point)
{
   double balance=0, equity=0, used=0, free=0;
   int positions=0;
   if(valid && Identity(reason))
   {
      ResetLastError();
      balance = AccountInfoDouble(ACCOUNT_BALANCE); equity = AccountInfoDouble(ACCOUNT_EQUITY);
      used = AccountInfoDouble(ACCOUNT_MARGIN); free = AccountInfoDouble(ACCOUNT_MARGIN_FREE);
      positions = PositionsTotal();
      if(GetLastError() != 0 || !MathIsValidNumber(balance) || !MathIsValidNumber(equity) || !MathIsValidNumber(used) ||
         !MathIsValidNumber(free) || used < 0 || positions < 0)
      { valid = false; reason = "account_metrics_invalid"; }
      if(!Identity(reason)) valid = false;
   }
   else valid = false;
   string line = "";
   Cell(line, Unsigned(++sequence)); Cell(line, valid ? "COLLECTING_ONLY" : "INVALID");
   Cell(line, "WAIT"); Cell(line, reason); Cell(line, Stamp(TimeGMT()));
   Cell(line, Stamp(TimeLocal())); Cell(line, Unsigned(GetTickCount64()));
   Cell(line, valid ? Stamp(TimeCurrent()) : "");
   Cell(line, valid ? Stamp(tick.time) : ""); Cell(line, valid ? Integer(tick.time_msc) : "");
   Cell(line, valid ? Integer((long)TimeTradeServer()-(long)tick.time) : "");
   Cell(line, valid ? Number(tick.bid) : ""); Cell(line, valid ? Number(tick.ask) : "");
   Cell(line, valid ? Number(tick.ask-tick.bid) : "");
   Cell(line, valid ? Number((tick.ask-tick.bid)/point) : ""); Cell(line, valid ? Number(point) : "");
   Cell(line, valid ? Number(balance) : ""); Cell(line, valid ? Number(equity) : "");
   Cell(line, valid ? Number(used) : ""); Cell(line, valid ? Number(free) : "");
   Cell(line, valid ? Integer(positions) : "");
   Cell(line, Truth((bool)TerminalInfoInteger(TERMINAL_CONNECTED)));
   Cell(line, "host_UTC_unverified"); Cell(line, "broker_server_offset_unverified");
   Cell(line, "false");
   return Line(heartbeat_handle, line);
}
void CloseAll()
{
   if(heartbeat_handle != INVALID_HANDLE) FileClose(heartbeat_handle);
   if(spec_handle != INVALID_HANDLE) FileClose(spec_handle);
   for(int i=0; i<3; ++i) if(bar_handles[i] != INVALID_HANDLE) FileClose(bar_handles[i]);
   if(lock_handle != INVALID_HANDLE) FileClose(lock_handle);
}
void OnStart()
{
   if(!EnableCollection) { Print("Evidence collector inactive; no files opened."); return; }
   if(ExpectedDemoLogin <= 0 || (bool)MQLInfoInteger(MQL_TESTER))
   { Print("Evidence collector requires local expected DEMO login and an actual terminal."); return; }
   // No FILE_SHARE_READ/FILE_SHARE_WRITE: another collector in this data directory fails closed.
   lock_handle = FileOpen("VortexEvidenceCollector.lock", FILE_READ | FILE_WRITE | FILE_BIN);
   if(lock_handle == INVALID_HANDLE)
   { Print("Evidence collector lock unavailable; another instance or filesystem error."); return; }
   run_folder = "VortexEvidence_" + Integer((long)TimeGMT()) + "_" + Unsigned(GetTickCount64());
   if(!FolderCreate(run_folder))
   { Print("Evidence collector cannot create new run directory."); CloseAll(); return; }
   heartbeat_handle = NewFile("heartbeat.csv");
   bar_handles[0] = NewFile("XAUUSD_M5.csv"); bar_handles[1] = NewFile("XAUUSD_M15.csv");
   bar_handles[2] = NewFile("XAUUSD_H1.csv");
   string header = "symbol,timeframe,bar_open_server,nominal_close_server,open,high,low,close,tick_volume,spread_points,real_volume,received_host_utc_label,receipt_monotonic_ms,closed_cutoff_tick_server,gap_before_seconds,source_time_basis,receipt_clock_accuracy";
   if(!disk_failed)
   {
      Line(heartbeat_handle, "sequence,status,action,reason,host_utc_label,host_local_label,receipt_monotonic_ms,broker_last_quote_server,source_tick_server,source_tick_msc_server,estimated_tick_age_server_seconds,bid,ask,spread_price,spread_points,point,balance_usd,equity_usd,margin_used_usd,margin_free_usd,all_account_positions_count,terminal_connected,host_clock_accuracy,source_time_basis,execution_enabled");
      for(int i=0; i<3; ++i) Line(bar_handles[i], header);
   }
   Print("Evidence collector started; private folder ", run_folder, "; no strategy or execution.");
   while(!IsStopped() && !disk_failed)
   {
      ulong cycle_start = GetTickCount64();
      string reason = "collection_only_no_strategy";
      MqlTick tick = {}; double point = 0;
      bool valid = Identity(reason) && Quote(tick, point, reason);
      if(valid && !anchored)
      {
         next_bar[0]=(datetime)(((long)tick.time/300)*300);
         next_bar[1]=(datetime)(((long)tick.time/900)*900);
         next_bar[2]=(datetime)(((long)tick.time/3600)*3600);
         anchored=true;
      }
      datetime cutoff = tick.time;
      MqlRates m5[], m15[], h1[];
      if(valid) valid = LoadBars(PERIOD_M5,0,cutoff,m5,reason) &&
                        LoadBars(PERIOD_M15,1,cutoff,m15,reason) && LoadBars(PERIOD_H1,2,cutoff,h1,reason);
      // Data reads may take time. Recheck identity and quote before recording metrics/bars.
      if(valid) valid = Identity(reason) && Quote(tick,point,reason);
      if(valid && !spec_written)
      {
         valid = SaveSpec(reason);
         if(valid) valid = Identity(reason);
         if(valid) spec_written=true;
      }
      if(valid) valid = SaveBars(PERIOD_M5,0,m5,cutoff,reason) && SaveBars(PERIOD_M15,1,m15,cutoff,reason) &&
                        SaveBars(PERIOD_H1,2,h1,cutoff,reason);
      if(IsStopped() || disk_failed) break;
      if(valid) valid = Identity(reason) && Quote(tick,point,reason);
      if(!Heartbeat(valid,reason,tick,point)) break;
      // 5 seconds is a target cadence; broker reads/disk latency can delay a sample.
      while(!IsStopped() && GetTickCount64()-cycle_start < (ulong)INTERVAL_MS) Sleep(100);
   }
   CloseAll();
   Print(disk_failed ? "Evidence collector stopped: disk write/flush failure; inspect private files." :
                      "Evidence collector stopped. No unattended service or reboot guarantee.");
}
