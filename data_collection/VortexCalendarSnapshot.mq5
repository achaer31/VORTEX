// One-shot prospective calendar capture. No account reads, orders, or settings changes.
#property strict
#property version "1.00"
#property description "Capture a USD calendar snapshot for offline review; never enables trading."
#property script_show_inputs

input int ServerUtcOffsetMinutes = 100000; // REQUIRED: independently verified for this query window.
input bool HostUtcClockVerified = false;   // Operator claim, not an automatic clock check.

bool write_failed = false;

string Iso(const datetime value)
{
   string text = TimeToString(value, TIME_DATE | TIME_SECONDS);
   StringReplace(text, ".", "-");
   StringReplace(text, " ", "T");
   return text;
}

string Csv(const string value)
{
   string text = value;
   StringReplace(text, "\"", "\"\"");
   return "\"" + text + "\"";
}

int Open(const string filename)
{
   return FileOpen(filename, FILE_WRITE | FILE_CSV | FILE_ANSI, ',', CP_UTF8);
}

void Meta(const int handle, const string key, const string value)
{
   if(FileWrite(handle, Csv(key), Csv(value)) == 0) write_failed = true;
}

void OnStart()
{
   if((bool)MQLInfoInteger(MQL_TESTER))
   {
      Print("Calendar capture refused: Strategy Tester cannot establish actual receipt times.");
      return;
   }
   if(ServerUtcOffsetMinutes < -840 || ServerUtcOffsetMinutes > 840)
   {
      Print("Calendar capture requires a verified server UTC offset; default is unknown.");
      return;
   }
   if(!(bool)TerminalInfoInteger(TERMINAL_CONNECTED))
   {
      Print("Calendar capture refused: terminal disconnected.");
      return;
   }

   datetime started = TimeGMT(); // Host UTC clock; its correctness is a separate prerequisite.
   datetime from_utc = (datetime)((long)started - 3600);
   datetime to_utc = (datetime)((long)started + 86400);
   long shift = (long)ServerUtcOffsetMinutes * 60;
   datetime from_server = (datetime)((long)from_utc + shift);
   datetime to_server = (datetime)((long)to_utc + shift);

   MqlCalendarValue values[];
   ResetLastError();
   int count = CalendarValueHistory(values, from_server, to_server, NULL, "USD");
   int query_error = GetLastError();
   MqlCalendarEvent events[];
   int lookup_errors[];
   int rows = count < 0 ? 0 : count;
   if(rows != ArraySize(values))
   {
      query_error = 5400;
      if(rows > ArraySize(values)) rows = ArraySize(values);
   }
   if(ArrayResize(events, rows) != rows || ArrayResize(lookup_errors, rows) != rows)
   {
      Print("Calendar capture failed: insufficient memory; no usable snapshot.");
      return;
   }
   int metadata_errors = 0;
   int ambiguous_high_times = 0;
   for(int i = 0; i < rows; ++i)
   {
      ResetLastError();
      bool ok = CalendarEventById(values[i].event_id, events[i]);
      lookup_errors[i] = ok ? 0 : GetLastError();
      if(!ok)
      {
         ++metadata_errors;
         if(lookup_errors[i] == 0) lookup_errors[i] = 5402;
      }
      else if(events[i].importance == CALENDAR_IMPORTANCE_HIGH &&
              events[i].time_mode != CALENDAR_TIMEMODE_DATETIME)
         ++ambiguous_high_times;
   }
   datetime received = TimeGMT(); // After ALL event metadata arrives; never event/publication time.
   bool connected = (bool)TerminalInfoInteger(TERMINAL_CONNECTED);
   bool complete = count >= 0 && query_error == 0 && metadata_errors == 0 &&
                   ambiguous_high_times == 0 && connected && received >= started;
   string folder = "VortexCalendar_" + IntegerToString((long)started) + "_" +
                   StringFormat("%I64u", GetTickCount64());
   if(!FolderCreate(folder))
   {
      Print("Calendar capture cannot create unique output folder.");
      return;
   }
   int out = Open(folder + "\\events.csv");
   if(out == INVALID_HANDLE)
   {
      Print("Calendar capture cannot open events file.");
      return;
   }
   if(FileWrite(out, "value_id", "event_id", "event_time_server", "importance", "time_mode",
                "title", "source_url", "metadata_error") == 0) write_failed = true;
   for(int i = 0; i < rows; ++i)
   {
      if(FileWrite(out, Csv(StringFormat("%I64u", values[i].id)),
                   Csv(StringFormat("%I64u", values[i].event_id)), Csv(Iso(values[i].time)),
                   Csv(lookup_errors[i] == 0 ? EnumToString(events[i].importance) : "UNKNOWN"),
                   Csv(lookup_errors[i] == 0 ? EnumToString(events[i].time_mode) : "UNKNOWN"),
                   Csv(lookup_errors[i] == 0 ? events[i].name : ""),
                   Csv(lookup_errors[i] == 0 ? events[i].source_url : ""),
                   Csv(IntegerToString(lookup_errors[i]))) == 0) write_failed = true;
   }
   ResetLastError();
   FileFlush(out);
   if(GetLastError() != 0) write_failed = true;
   FileClose(out);

   int manifest = Open(folder + "\\manifest.csv");
   if(manifest == INVALID_HANDLE)
   {
      Print("Calendar capture has no manifest; do not ingest output.");
      return;
   }
   Meta(manifest, "key", "value");
   Meta(manifest, "schema", "vortex.calendar.snapshot.v1");
   Meta(manifest, "origin", "actual_terminal_capture");
   Meta(manifest, "currency_filter", "USD");
   Meta(manifest, "started_at_utc", Iso(started) + "Z");
   Meta(manifest, "received_at_utc", Iso(received) + "Z");
   Meta(manifest, "query_start_utc", Iso(from_utc) + "Z");
   Meta(manifest, "query_end_utc", Iso(to_utc) + "Z");
   Meta(manifest, "server_utc_offset_minutes", IntegerToString(ServerUtcOffsetMinutes));
   Meta(manifest, "host_utc_clock_verified", HostUtcClockVerified ? "true" : "false");
   Meta(manifest, "terminal_connected", connected ? "true" : "false");
   Meta(manifest, "query_error", IntegerToString(query_error));
   Meta(manifest, "rows", IntegerToString(rows));
   Meta(manifest, "metadata_errors", IntegerToString(metadata_errors));
   Meta(manifest, "ambiguous_high_times", IntegerToString(ambiguous_high_times));
   Meta(manifest, "coverage_attested", "false"); // Successful query does not prove provider completeness.
   Meta(manifest, "run_status", complete && !write_failed ? "captured_needs_review" : "data_issues");
   ResetLastError();
   FileFlush(manifest);
   if(GetLastError() != 0) write_failed = true;
   FileClose(manifest);
   Print("Calendar snapshot folder: ", folder, "; ",
         complete && !write_failed ? "captured, coverage not verified" : "FAILED / data issues");
}
