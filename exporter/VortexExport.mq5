// Vortex: manual, market-data-only export. No orders or account changes.
#property strict
#property version   "1.00"
#property description "Export closed XAUUSD M5/M15/H1 bars and non-identifying metadata."
#property script_show_inputs

input string ExportSymbol = "";  // Empty uses the chart symbol; must start with XAUUSD.
input int    HistoryDays = 180; // Calendar days in the broker's server clock; 1..366.

const string TIME_BASIS = "broker_server_unknown_offset";
bool write_failed = false;
bool data_issues = false;

string Csv(const string text)
{
   string escaped = text;
   StringReplace(escaped, "\"", "\"\"");
   return "\"" + escaped + "\"";
}

string BoolText(const bool value) { return value ? "true" : "false"; }
string IntText(const long value) { return StringFormat("%I64d", value); }

string IsoServer(const datetime value)
{
   if(value <= 0) return "";
   string result = TimeToString(value, TIME_DATE | TIME_SECONDS);
   StringReplace(result, ".", "-");
   StringReplace(result, " ", "T");
   return result; // No Z or UTC offset: the historical server offset is unknown.
}

string SafeName(const string value)
{
   string result = "";
   for(int i = 0; i < StringLen(value); ++i)
   {
      ushort c = StringGetCharacter(value, i);
      bool allowed = ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
                      (c >= '0' && c <= '9') || c == '_' || c == '-');
      result += allowed ? StringSubstr(value, i, 1) : "_";
   }
   return result;
}

int OpenCsv(const string name)
{
   ResetLastError();
   int handle = FileOpen(name, FILE_WRITE | FILE_CSV | FILE_ANSI, ',', CP_UTF8);
   if(handle == INVALID_HANDLE)
      Print("VortexExport: cannot create file; error ", GetLastError());
   return handle;
}

bool Record(const int handle, const string scope, const string key,
            const string value, const string status = "ok")
{
   ResetLastError();
   if(FileWrite(handle, Csv(scope), Csv(key), Csv(value), Csv(status)) == 0)
   {
      write_failed = true;
      Print("VortexExport: file write failed; error ", GetLastError());
      return false;
   }
   return true;
}

void MetaInteger(const int handle, const string symbol,
                 const string key, const ENUM_SYMBOL_INFO_INTEGER property)
{
   long value = 0;
   ResetLastError();
   bool ok = SymbolInfoInteger(symbol, property, value);
   int error = GetLastError();
   Record(handle, "symbol", key, ok ? IntText(value) : "",
          ok ? "ok" : "unavailable_error_" + IntegerToString(error));
}

void MetaDouble(const int handle, const string symbol,
                const string key, const ENUM_SYMBOL_INFO_DOUBLE property)
{
   double value = 0;
   ResetLastError();
   bool ok = SymbolInfoDouble(symbol, property, value);
   int error = GetLastError();
   Record(handle, "symbol", key, ok ? DoubleToString(value, 16) : "",
          ok ? "ok" : "unavailable_error_" + IntegerToString(error));
}

void MetaString(const int handle, const string symbol,
                const string key, const ENUM_SYMBOL_INFO_STRING property)
{
   string value = "";
   ResetLastError();
   bool ok = SymbolInfoString(symbol, property, value);
   int error = GetLastError();
   Record(handle, "symbol", key, ok ? value : "",
          ok ? "ok" : "unavailable_error_" + IntegerToString(error));
}

bool WriteMetadata(const string folder, const string symbol, const datetime snapshot)
{
   int handle = OpenCsv(folder + "\\metadata.csv");
   if(handle == INVALID_HANDLE) return false;
   Record(handle, "scope", "key", "value", "status");
   Record(handle, "export", "schema_version", "1");
   Record(handle, "export", "symbol", symbol);
   Record(handle, "export", "snapshot_server_time", IsoServer(snapshot));
   Record(handle, "export", "timezone", TIME_BASIS, "unknown_offset_and_dst");
   Record(handle, "export", "snapshot_clock", "TimeCurrent: last known server quote time; may be stale");
   Record(handle, "export", "requested_history_days", IntegerToString(HistoryDays));
   Record(handle, "terminal", "build", IntText(TerminalInfoInteger(TERMINAL_BUILD)));
   Record(handle, "terminal", "max_bars", IntText(TerminalInfoInteger(TERMINAL_MAXBARS)));
   Record(handle, "terminal", "connected", BoolText((bool)TerminalInfoInteger(TERMINAL_CONNECTED)));
   Record(handle, "terminal", "algorithmic_trading_enabled", BoolText((bool)TerminalInfoInteger(TERMINAL_TRADE_ALLOWED)));
   ResetLastError();
   string currency = AccountInfoString(ACCOUNT_CURRENCY);
   int currency_error = GetLastError();
   Record(handle, "account", "currency", currency,
          currency != "" && currency_error == 0 ? "ok" : "unavailable_or_unverified");
   MetaString(handle, symbol, "currency_base", SYMBOL_CURRENCY_BASE);
   MetaString(handle, symbol, "currency_profit", SYMBOL_CURRENCY_PROFIT);
   MetaString(handle, symbol, "currency_margin", SYMBOL_CURRENCY_MARGIN);
   MetaInteger(handle, symbol, "digits", SYMBOL_DIGITS);
   MetaInteger(handle, symbol, "chart_mode_enum", SYMBOL_CHART_MODE);
   MetaInteger(handle, symbol, "execution_mode_enum", SYMBOL_TRADE_EXEMODE);
   MetaInteger(handle, symbol, "calculation_mode_enum", SYMBOL_TRADE_CALC_MODE);
   MetaInteger(handle, symbol, "trade_mode_enum", SYMBOL_TRADE_MODE);
   MetaInteger(handle, symbol, "filling_mode_bitmask", SYMBOL_FILLING_MODE);
   MetaInteger(handle, symbol, "spread_points_snapshot", SYMBOL_SPREAD);
   MetaInteger(handle, symbol, "spread_is_floating", SYMBOL_SPREAD_FLOAT);
   MetaInteger(handle, symbol, "stops_level_points", SYMBOL_TRADE_STOPS_LEVEL);
   MetaInteger(handle, symbol, "freeze_level_points", SYMBOL_TRADE_FREEZE_LEVEL);
   MetaInteger(handle, symbol, "swap_mode_enum", SYMBOL_SWAP_MODE);
   MetaInteger(handle, symbol, "swap_triple_day_enum", SYMBOL_SWAP_ROLLOVER3DAYS);
   MetaDouble(handle, symbol, "point", SYMBOL_POINT);
   MetaDouble(handle, symbol, "contract_size", SYMBOL_TRADE_CONTRACT_SIZE);
   MetaDouble(handle, symbol, "tick_size", SYMBOL_TRADE_TICK_SIZE);
   MetaDouble(handle, symbol, "tick_value", SYMBOL_TRADE_TICK_VALUE);
   MetaDouble(handle, symbol, "tick_value_profit", SYMBOL_TRADE_TICK_VALUE_PROFIT);
   MetaDouble(handle, symbol, "tick_value_loss", SYMBOL_TRADE_TICK_VALUE_LOSS);
   MetaDouble(handle, symbol, "volume_min_lots", SYMBOL_VOLUME_MIN);
   MetaDouble(handle, symbol, "volume_max_lots", SYMBOL_VOLUME_MAX);
   MetaDouble(handle, symbol, "volume_step_lots", SYMBOL_VOLUME_STEP);
   MetaDouble(handle, symbol, "volume_limit_lots", SYMBOL_VOLUME_LIMIT);
   MetaDouble(handle, symbol, "swap_long", SYMBOL_SWAP_LONG);
   MetaDouble(handle, symbol, "swap_short", SYMBOL_SWAP_SHORT);
   MetaDouble(handle, symbol, "swap_sunday_multiplier", SYMBOL_SWAP_SUNDAY);
   MetaDouble(handle, symbol, "swap_monday_multiplier", SYMBOL_SWAP_MONDAY);
   MetaDouble(handle, symbol, "swap_tuesday_multiplier", SYMBOL_SWAP_TUESDAY);
   MetaDouble(handle, symbol, "swap_wednesday_multiplier", SYMBOL_SWAP_WEDNESDAY);
   MetaDouble(handle, symbol, "swap_thursday_multiplier", SYMBOL_SWAP_THURSDAY);
   MetaDouble(handle, symbol, "swap_friday_multiplier", SYMBOL_SWAP_FRIDAY);
   MetaDouble(handle, symbol, "swap_saturday_multiplier", SYMBOL_SWAP_SATURDAY);
   Record(handle, "export", "commission", "", "not_available_from_symbol_properties");
   Record(handle, "export", "metadata_scope", "current_snapshot_not_historical_contract_or_cost_schedule");
   Record(handle, "export", "private_account_identifiers_exported", "false");
   FileFlush(handle);
   FileClose(handle);
   return !write_failed;
}

bool ExportTimeframe(const int manifest, const string folder, const string symbol,
                     const ENUM_TIMEFRAMES timeframe, const datetime snapshot,
                     const datetime requested_start, const int digits)
{
   string label = EnumToString(timeframe);
   StringReplace(label, "PERIOD_", "");
   int seconds = PeriodSeconds(timeframe);
   datetime boundary = (datetime)(((long)snapshot / seconds) * seconds);
   datetime requested_stop = boundary - 1;
   string filename = SafeName(symbol) + "_" + label + ".csv";
   Record(manifest, label, "filename", filename);
   Record(manifest, label, "requested_start_server", IsoServer(requested_start));
   Record(manifest, label, "requested_end_exclusive_server", IsoServer(boundary));
   Record(manifest, label, "period_seconds", IntegerToString(seconds));

   MqlRates bars[];
   ArraySetAsSeries(bars, false);
   // Exactly one request: no polling or retry loop. MT5 may wait internally.
   ResetLastError();
   ulong started = GetTickCount64();
   int copied = CopyRates(symbol, timeframe, requested_start, requested_stop, bars);
   int copy_error = GetLastError();
   ulong elapsed = GetTickCount64() - started;
   long synced = 0, first_available = 0, server_first = 0, latest_bar = 0;
   bool synced_known = SeriesInfoInteger(symbol, timeframe, SERIES_SYNCHRONIZED, synced);
   bool first_known = SeriesInfoInteger(symbol, timeframe, SERIES_FIRSTDATE, first_available);
   bool server_first_known = SeriesInfoInteger(symbol, timeframe, SERIES_SERVER_FIRSTDATE, server_first);
   bool latest_known = SeriesInfoInteger(symbol, timeframe, SERIES_LASTBAR_DATE, latest_bar);
   // Also exclude the latest MT5 bar (bar 0), even when the market is closed.
   datetime closed_boundary = boundary;
   if(latest_known && latest_bar > 0 && latest_bar < (long)closed_boundary)
      closed_boundary = (datetime)latest_bar;

   Record(manifest, label, "copy_rates_return", IntegerToString(copied));
   Record(manifest, label, "copy_rates_error", IntegerToString(copy_error));
   Record(manifest, label, "copy_elapsed_ms", StringFormat("%I64u", elapsed));
   Record(manifest, label, "series_synchronized", BoolText(synced_known && synced != 0), synced_known ? "ok" : "unknown");
   Record(manifest, label, "terminal_first_bar_server", first_known ? IsoServer((datetime)first_available) : "", first_known ? "ok" : "unknown");
   Record(manifest, label, "server_first_bar_server", server_first_known ? IsoServer((datetime)server_first) : "", server_first_known ? "ok" : "unknown");
   Record(manifest, label, "latest_series_bar_open_server", latest_known ? IsoServer((datetime)latest_bar) : "", latest_known ? "ok" : "unknown");
   Record(manifest, label, "effective_closed_end_exclusive_server", IsoServer(closed_boundary));

   int handle = OpenCsv(folder + "\\" + filename);
   if(handle == INVALID_HANDLE)
   {
      data_issues = true;
      Record(manifest, label, "export_status", "file_open_failed", "error");
      Record(manifest, label, "history_incomplete", "true");
      Record(manifest, label, "actual_count", "0");
      return false;
   }
   if(FileWrite(handle, "bar_open_server", "timezone", "symbol", "timeframe",
                "open", "high", "low", "close", "tick_volume", "spread_points",
                "real_volume") == 0)
   {
      data_issues = true;
      FileClose(handle);
      Record(manifest, label, "export_status", "header_write_failed", "error");
      Record(manifest, label, "history_incomplete", "true");
      Record(manifest, label, "actual_count", "0");
      return false;
   }
   int count = 0, skipped = 0, invalid = 0, gaps = 0;
   long max_gap = 0;
   datetime first = 0, last = 0;
   bool file_error = false, interrupted = false;
   for(int i = 0; i < copied; ++i)
   {
      if(IsStopped()) { interrupted = true; break; }
      datetime t = bars[i].time;
      if(t < requested_start || t >= closed_boundary || t + seconds > snapshot)
      { ++skipped; continue; }
      bool good = (t > 0 && (last == 0 || t > last) &&
                   MathIsValidNumber(bars[i].open) && MathIsValidNumber(bars[i].high) &&
                   MathIsValidNumber(bars[i].low) && MathIsValidNumber(bars[i].close) &&
                   bars[i].low > 0 && bars[i].low <= bars[i].open &&
                   bars[i].low <= bars[i].close && bars[i].high >= bars[i].open &&
                   bars[i].high >= bars[i].close && bars[i].tick_volume >= 0 &&
                   bars[i].spread >= 0 && bars[i].real_volume >= 0);
      if(!good) { ++invalid; continue; }
      ResetLastError();
      uint written = FileWrite(handle, IsoServer(t), TIME_BASIS, Csv(symbol), label,
                               DoubleToString(bars[i].open, digits), DoubleToString(bars[i].high, digits),
                               DoubleToString(bars[i].low, digits), DoubleToString(bars[i].close, digits),
                               IntText(bars[i].tick_volume), IntegerToString(bars[i].spread),
                               IntText(bars[i].real_volume));
      if(written == 0) { file_error = true; break; }
      if(last > 0 && t - last > seconds)
      {
         ++gaps;
         if(t - last > max_gap) max_gap = t - last;
      }
      if(count == 0) first = t;
      last = t;
      ++count;
   }
   FileFlush(handle);
   FileClose(handle);
   ArrayFree(bars);

   bool start_short = (count == 0 || first > requested_start + seconds);
   bool end_short = (count == 0 || last + seconds < closed_boundary);
   bool issue = (copied <= 0 || copy_error != 0 || !synced_known || synced == 0 ||
                 !latest_known || latest_bar <= 0 || invalid > 0 || file_error ||
                 interrupted || start_short || end_short);
   if(issue) data_issues = true;
   Record(manifest, label, "actual_count", IntegerToString(count));
   Record(manifest, label, "actual_first_open_server", IsoServer(first));
   Record(manifest, label, "actual_last_open_server", IsoServer(last));
   Record(manifest, label, "skipped_open_or_out_of_range_count", IntegerToString(skipped));
   Record(manifest, label, "rejected_invalid_or_nonascending_count", IntegerToString(invalid));
   Record(manifest, label, "observed_gap_count", IntegerToString(gaps));
   Record(manifest, label, "largest_gap_seconds", IntText(max_gap));
   Record(manifest, label, "start_coverage_short", BoolText(start_short));
   Record(manifest, label, "end_coverage_short", BoolText(end_short));
   Record(manifest, label, "history_incomplete", issue ? "true" : "unknown", "conservative_not_a_completeness_certificate");
   Record(manifest, label, "completeness_verified", "false");
   Record(manifest, label, "export_status", file_error ? "file_write_failed" : (interrupted ? "interrupted" : (count > 0 ? "exported_available_bars" : "no_closed_bars")));
   Record(manifest, label, "gap_interpretation", "market_closures_and_missing_data_not_distinguished");
   FileFlush(manifest);
   Print("VortexExport ", label, ": ", count, " bars; history_incomplete=", issue ? "true" : "unknown");
   return count > 0 && !file_error && !interrupted;
}

void OnStart()
{
   string symbol = ExportSymbol;
   StringTrimLeft(symbol);
   StringTrimRight(symbol);
   if(symbol == "") symbol = _Symbol;
   string upper = symbol;
   StringToUpper(upper);
   if(StringFind(upper, "XAUUSD") != 0)
   {
      Print("VortexExport stopped: choose an XAUUSD chart or enter its exact broker symbol.");
      return;
   }
   if(HistoryDays < 1 || HistoryDays > 366)
   {
      Print("VortexExport stopped: HistoryDays must be 1..366.");
      return;
   }
   // Require an existing selected broker symbol; do not alter Market Watch.
   long exists = 0, selected = 0, custom = 0, digits_value = 0;
   if(!SymbolInfoInteger(symbol, SYMBOL_EXIST, exists) || exists == 0 ||
      !SymbolInfoInteger(symbol, SYMBOL_SELECT, selected) || selected == 0 ||
      !SymbolInfoInteger(symbol, SYMBOL_CUSTOM, custom) || custom != 0 ||
      !SymbolInfoInteger(symbol, SYMBOL_DIGITS, digits_value) || digits_value < 0 || digits_value > 16)
   {
      Print("VortexExport stopped: select an existing broker XAUUSD symbol in Market Watch first.");
      return;
   }
   string base_currency = SymbolInfoString(symbol, SYMBOL_CURRENCY_BASE);
   string profit_currency = SymbolInfoString(symbol, SYMBOL_CURRENCY_PROFIT);
   if(base_currency != "XAU" || profit_currency != "USD")
   {
      Print("VortexExport stopped: symbol currency metadata does not confirm XAU/USD.");
      return;
   }
   if(!TerminalInfoInteger(TERMINAL_CONNECTED))
   {
      Print("VortexExport stopped: terminal is offline; connect and refresh broker quotes first.");
      return;
   }
   datetime snapshot = TimeCurrent();
   if(snapshot <= 0)
   {
      Print("VortexExport stopped: broker server time is unavailable.");
      return;
   }
   datetime requested_start = (datetime)((long)snapshot - (long)HistoryDays * 86400);
   string run_id = SafeName(IsoServer(snapshot)) + "_" + StringFormat("%I64u", GetTickCount64());
   string folder = "VortexExport\\" + SafeName(symbol) + "_" + run_id;
   int manifest = OpenCsv(folder + "\\manifest.csv");
   if(manifest == INVALID_HANDLE) return;
   Record(manifest, "scope", "key", "value", "status");
   Record(manifest, "export", "schema_version", "1");
   Record(manifest, "export", "symbol", symbol);
   Record(manifest, "export", "timezone", TIME_BASIS, "unknown_offset_and_dst");
   Record(manifest, "export", "snapshot_server_time", IsoServer(snapshot));
   Record(manifest, "export", "terminal_build", IntText(TerminalInfoInteger(TERMINAL_BUILD)));
   Record(manifest, "export", "requested_history_days", IntegerToString(HistoryDays));
   Record(manifest, "export", "closed_bar_rule", "exclude snapshot interval and latest known MT5 bar; bar nominal end must not exceed snapshot");
   Record(manifest, "export", "retry_policy", "one CopyRates call per timeframe; no automatic retry");
   Record(manifest, "export", "run_status", "started");
   FileFlush(manifest);
   bool metadata_ok = WriteMetadata(folder, symbol, snapshot);
   Record(manifest, "export", "metadata_written", BoolText(metadata_ok));
   bool m5 = false, m15 = false, h1 = false;
   if(!IsStopped() && !write_failed) m5 = ExportTimeframe(manifest, folder, symbol, PERIOD_M5, snapshot, requested_start, (int)digits_value);
   if(!IsStopped() && !write_failed) m15 = ExportTimeframe(manifest, folder, symbol, PERIOD_M15, snapshot, requested_start, (int)digits_value);
   if(!IsStopped() && !write_failed) h1 = ExportTimeframe(manifest, folder, symbol, PERIOD_H1, snapshot, requested_start, (int)digits_value);
   Record(manifest, "export", "all_timeframes_have_written_bars", BoolText(m5 && m15 && h1));
   string run_status = IsStopped() ? "interrupted" :
                       (write_failed ? "write_error" :
                        ((!metadata_ok || !m5 || !m15 || !h1 || data_issues) ?
                         "finished_with_data_issues" : "finished"));
   Record(manifest, "export", "run_status", run_status);
   FileFlush(manifest);
   FileClose(manifest);
   Print("VortexExport: results under File > Open Data Folder > MQL5 > Files > ", folder);
}
