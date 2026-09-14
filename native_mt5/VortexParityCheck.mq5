// SYNTHETIC / OFFLINE ONLY. Supplied CSV arrays; no account, broker, network or order APIs.
#property strict
#property version "1.00"
#property description "Disabled-by-default offline native/Python signal parity harness."
#property script_show_inputs
#include "VortexSignalCore.mqh"

input bool EnableOfflineParity = false;
input string FixtureDirectory = "VortexParityFixtures"; // One safe folder name in MQL5/Files.

const string HARNESS_VERSION = "VORTEX-NATIVE-PARITY-0.1";
const string FIXTURE_KIND = "SYNTHETIC_OFFLINE_PARITY_V1";
const int MAX_FRAME_ROWS = 50000;
const int MAX_CASES = 32;
const int MAX_MODE_CASES = 512;
string result_folder = "";
bool output_failed = false;
long total_signal_rows = 0;
long total_mode_cases = 0;
long total_mode_results = 0;

bool SafeName(const string name)
{
   int n = StringLen(name);
   if(n < 1 || n > 48) return false;
   for(int i=0; i<n; ++i)
   {
      ushort c = StringGetCharacter(name,i);
      if(!((c>='A' && c<='Z') || (c>='a' && c<='z') ||
           (c>='0' && c<='9') || c=='_' || c=='-')) return false;
   }
   return true;
}
string IntText(const long value) { return StringFormat("%I64d",value); }
string BoolText(const bool value) { return value ? "1" : "0"; }
string FloatText(const double value) { return VxValid(value) ? DoubleToString(value,16) : ""; }
string TimeText(const datetime value) { return value == 0 ? "" : IntText((long)value); }
void Cell(string &line,const string value)
{
   string escaped=value;
   StringReplace(escaped,"\"","\"\"");
   if(line!="") line+=",";
   line+="\""+escaped+"\"";
}
bool WriteLine(const int h,const string line)
{
   uchar bytes[];
   int count=StringToCharArray(line+"\r\n",bytes,0,WHOLE_ARRAY,CP_UTF8);
   if(h==INVALID_HANDLE || count<=1) { output_failed=true; return false; }
   ResetLastError();
   uint written=FileWriteArray(h,bytes,0,(uint)(count-1));
   if(written!=(uint)(count-1) || GetLastError()!=0) { output_failed=true; return false; }
   return true;
}
bool FinishFile(const int h)
{
   if(h==INVALID_HANDLE) return false;
   ResetLastError();
   FileFlush(h);
   if(GetLastError()!=0) output_failed=true;
   FileClose(h);
   return !output_failed;
}
int OutputFile(const string name)
{
   int h=FileOpen(result_folder+"\\"+name,FILE_WRITE|FILE_BIN);
   if(h==INVALID_HANDLE) output_failed=true;
   return h;
}
int InputFile(const string name,string &error)
{
   int h=FileOpen(FixtureDirectory+"\\"+name,FILE_READ|FILE_TXT|FILE_ANSI,0,CP_UTF8);
   if(h==INVALID_HANDLE) { error="fixture_file_unavailable"; return h; }
   if(FileSize(h)>33554432)
   { FileClose(h); error="fixture_file_too_large"; return INVALID_HANDLE; }
   return h;
}
bool Header(const int h,const string expected,string &error)
{
   if(FileIsEnding(h)) { error="missing_header"; return false; }
   string line=FileReadString(h);
   if(StringLen(line)>0 && StringGetCharacter(line,0)==65279) line=StringSubstr(line,1);
   if(line!=expected) { error="fixture_header_mismatch"; return false; }
   return true;
}
bool Fields(const string line,const int count,string &fields[],string &error)
{
   // Generator input is deliberately unquoted numeric/enum CSV; no arbitrary text fields.
   if(StringFind(line,"\"")>=0 || StringSplit(line,',',fields)!=count)
   { error="fixture_csv_width_or_quoting"; return false; }
   return true;
}
bool Digit(const ushort value) { return value>='0' && value<='9'; }
bool Numeric(const string text,const bool required,double &value)
{
   if(text=="") { value=EMPTY_VALUE; return !required; }
   int n=StringLen(text),i=0;
   if(StringGetCharacter(text,i)=='+' || StringGetCharacter(text,i)=='-') ++i;
   bool digits=false;
   while(i<n && Digit(StringGetCharacter(text,i))) { digits=true; ++i; }
   if(i<n && StringGetCharacter(text,i)=='.')
   {
      ++i;
      while(i<n && Digit(StringGetCharacter(text,i))) { digits=true; ++i; }
   }
   if(!digits) return false;
   if(i<n && (StringGetCharacter(text,i)=='e' || StringGetCharacter(text,i)=='E'))
   {
      ++i;
      if(i<n && (StringGetCharacter(text,i)=='+' || StringGetCharacter(text,i)=='-')) ++i;
      int exponent_start=i;
      while(i<n && Digit(StringGetCharacter(text,i))) ++i;
      if(i==exponent_start) return false;
   }
   if(i!=n) return false;
   value=StringToDouble(text);
   return VxValid(value);
}
bool IntegerValue(const string text,long &value)
{
   double number=0;
   if(!Numeric(text,true,number) || MathAbs(number)>9000000000000000.0 || MathFloor(number)!=number)
      return false;
   value=(long)number;
   return true;
}
bool Flag(const string text,bool &value)
{
   if(text!="0" && text!="1") return false;
   value=text=="1";
   return true;
}
bool LoadCases(string &cases[],string &error)
{
   ArrayResize(cases,0);
   int h=InputFile("cases.csv",error);
   if(h==INVALID_HANDLE) return false;
   bool ok=Header(h,"case_id",error);
   while(ok && !FileIsEnding(h) && !IsStopped())
   {
      string name=FileReadString(h);
      if(name=="" && FileIsEnding(h)) break;
      if(!SafeName(name) || ArraySize(cases)>=MAX_CASES) { error="invalid_case_id_or_count"; ok=false; break; }
      for(int i=0;i<ArraySize(cases);++i) if(cases[i]==name) { error="duplicate_case_id"; ok=false; break; }
      if(!ok) break;
      int n=ArraySize(cases);
      if(ArrayResize(cases,n+1)!=n+1) { error="memory_allocation_failed"; ok=false; break; }
      cases[n]=name;
   }
   FileClose(h);
   if(ArraySize(cases)==0) { error="no_cases"; return false; }
   return ok && !IsStopped();
}
bool LoadRates(const string filename,MqlRates &rates[],string &error)
{
   ArrayResize(rates,0); ArraySetAsSeries(rates,false);
   int h=InputFile(filename,error);
   if(h==INVALID_HANDLE) return false;
   bool ok=Header(h,"epoch_utc,open,high,low,close,tick_volume,spread_points,real_volume",error);
   long previous=0;
   while(ok && !FileIsEnding(h) && !IsStopped())
   {
      string line=FileReadString(h),f[];
      if(line=="" && FileIsEnding(h)) break;
      if(!Fields(line,8,f,error)) { ok=false; break; }
      MqlRates row={}; long epoch=0,spread=0;
      ok=IntegerValue(f[0],epoch) && epoch>previous &&
         Numeric(f[1],true,row.open) && Numeric(f[2],true,row.high) &&
         Numeric(f[3],true,row.low) && Numeric(f[4],true,row.close) &&
         IntegerValue(f[5],row.tick_volume) && IntegerValue(f[6],spread) &&
         IntegerValue(f[7],row.real_volume);
      if(!ok || spread<0 || spread>2147483647 || row.tick_volume<0 || row.real_volume<0 ||
         row.low<=0 || row.low>MathMin(row.open,row.close) || row.high<MathMax(row.open,row.close))
      { error="invalid_fixture_bar"; ok=false; break; }
      row.time=(datetime)epoch; row.spread=(int)spread;
      int n=ArraySize(rates);
      if(n>=MAX_FRAME_ROWS || ArrayResize(rates,n+1,1024)!=n+1)
      { error="frame_row_limit_or_memory"; ok=false; break; }
      rates[n]=row; previous=epoch;
   }
   FileClose(h);
   if(ArraySize(rates)==0) { error="empty_fixture_frame"; return false; }
   return ok && !IsStopped();
}
bool LoadExternal(const string filename,VxExternal &external[],string &error)
{
   ArrayResize(external,0);
   int h=InputFile(filename,error);
   if(h==INVALID_HANDLE) return false;
   bool ok=Header(h,"decision_epoch,news_valid,news_blocked,macro_valid,session_valid,session_ideal,dxy_roc,us10y_change,asia_high,asia_low,london_high,london_low,newyork_high,newyork_low",error);
   long previous=0;
   while(ok && !FileIsEnding(h) && !IsStopped())
   {
      string line=FileReadString(h),f[];
      if(line=="" && FileIsEnding(h)) break;
      if(!Fields(line,14,f,error)) { ok=false; break; }
      VxExternal row; VxResetExternal(row); long epoch=0;
      ok=IntegerValue(f[0],epoch) && epoch>previous && Flag(f[1],row.newsValid) &&
         Flag(f[2],row.newsBlocked) && Flag(f[3],row.macroValid) &&
         Flag(f[4],row.sessionValid) && Flag(f[5],row.sessionIdeal) &&
         Numeric(f[6],false,row.dxyRoc) && Numeric(f[7],false,row.us10yChange) &&
         Numeric(f[8],false,row.asiaHigh) && Numeric(f[9],false,row.asiaLow) &&
         Numeric(f[10],false,row.londonHigh) && Numeric(f[11],false,row.londonLow) &&
         Numeric(f[12],false,row.newyorkHigh) && Numeric(f[13],false,row.newyorkLow);
      if(!ok) { error="invalid_external_fixture"; break; }
      row.decisionTime=(datetime)epoch;
      int n=ArraySize(external);
      if(n>=MAX_FRAME_ROWS || ArrayResize(external,n+1,1024)!=n+1)
      { error="external_row_limit_or_memory"; ok=false; break; }
      external[n]=row; previous=epoch;
   }
   FileClose(h);
   return ok && !IsStopped(); // Header-only means intentionally missing external context.
}
bool SaveSignals(const string case_id,VxSignal &rows[],string &error)
{
   int h=OutputFile(case_id+"_signals.csv");
   if(h==INVALID_HANDLE) { error="output_open_failed"; return false; }
   bool ok=WriteLine(h,"bar_open_epoch,decision_epoch,m15_closed_epoch,h1_closed_epoch,h4_closed_epoch,orion,vortex,nova,luna,kira,atlas,consensus,atr,stop_long,stop_short,swing_low,swing_high,orion_reason,vortex_reason,nova_reason,luna_reason,kira_reason,atlas_reason,mode,signal,h1_alignment,h4_alignment,m15_fresh,h1_fresh,h4_fresh,execution_valid,ready");
   for(int i=0;ok && i<ArraySize(rows) && !IsStopped();++i)
   {
      VxSignal r=rows[i]; string line="";
      Cell(line,TimeText(r.barOpen)); Cell(line,TimeText(r.decisionTime));
      Cell(line,TimeText(r.m15ClosedAt)); Cell(line,TimeText(r.h1ClosedAt)); Cell(line,TimeText(r.h4ClosedAt));
      Cell(line,FloatText(r.orion)); Cell(line,FloatText(r.vortex)); Cell(line,FloatText(r.nova));
      Cell(line,FloatText(r.luna)); Cell(line,FloatText(r.kira)); Cell(line,FloatText(r.atlas));
      Cell(line,FloatText(r.consensus)); Cell(line,FloatText(r.atr));
      Cell(line,FloatText(r.stopLong)); Cell(line,FloatText(r.stopShort));
      Cell(line,FloatText(r.swingLow)); Cell(line,FloatText(r.swingHigh));
      Cell(line,r.orionReason); Cell(line,r.vortexReason); Cell(line,r.novaReason);
      Cell(line,r.lunaReason); Cell(line,r.kiraReason); Cell(line,r.atlasReason);
      Cell(line,r.mode); Cell(line,IntText(r.signal));
      Cell(line,r.h1ClosedAt==0 ? "" : IntText(r.h1Alignment));
      Cell(line,r.h4ClosedAt==0 ? "" : IntText(r.h4Alignment));
      Cell(line,BoolText(r.m15Fresh)); Cell(line,BoolText(r.h1Fresh)); Cell(line,BoolText(r.h4Fresh));
      Cell(line,BoolText(r.executionValid)); Cell(line,BoolText(r.ready));
      ok=WriteLine(h,line);
      if(ok) ++total_signal_rows;
   }
   bool flushed=FinishFile(h);
   if(!ok || !flushed) error="output_write_failed";
   return ok && flushed && !IsStopped();
}
bool ModeCases(string &error)
{
   int mode_input=InputFile("mode_cases.csv",error);
   if(mode_input==INVALID_HANDLE) return false;
   bool ok=Header(mode_input,"case_id,orion,vortex,nova,luna,kira,atlas,consensus,h1_alignment,h4_alignment,session_ideal,eligible",error);
   int out=OutputFile("mode_results.csv");
   if(out==INVALID_HANDLE) { FileClose(mode_input); error="output_open_failed"; return false; }
   ok=ok && WriteLine(out,"case_id,mode,signal");
   string ids[];
   while(ok && !FileIsEnding(mode_input) && !IsStopped())
   {
      string line=FileReadString(mode_input),f[];
      if(line=="" && FileIsEnding(mode_input)) break;
      if(!Fields(line,12,f,error)) { ok=false; break; }
      VxSignal row={}; long h1=0,h4=0; bool ideal=false,eligible=false;
      ok=SafeName(f[0]) && Numeric(f[1],false,row.orion) && Numeric(f[2],false,row.vortex) &&
         Numeric(f[3],false,row.nova) && Numeric(f[4],false,row.luna) && Numeric(f[5],false,row.kira) &&
         Numeric(f[6],false,row.atlas) && Numeric(f[7],false,row.consensus) &&
         IntegerValue(f[8],h1) && IntegerValue(f[9],h4) && h1>=-1 && h1<=1 && h4>=-1 && h4<=1 &&
         Flag(f[10],ideal) && Flag(f[11],eligible);
      for(int j=0;ok && j<ArraySize(ids);++j) if(ids[j]==f[0]) ok=false;
      if(!ok) { error="invalid_or_duplicate_mode_case"; break; }
      int n=ArraySize(ids);
      if(n>=MAX_MODE_CASES || ArrayResize(ids,n+1)!=n+1)
      { error="mode_case_limit_or_memory"; ok=false; break; }
      ids[n]=f[0]; ++total_mode_cases;
      row.h1Alignment=(int)h1; row.h4Alignment=(int)h4;
      VxChooseMode(row,ideal,eligible);
      string result=""; Cell(result,f[0]); Cell(result,row.mode); Cell(result,IntText(row.signal));
      ok=WriteLine(out,result);
      if(ok) ++total_mode_results;
   }
   FileClose(mode_input);
   bool flushed=FinishFile(out);
   if(!flushed) error="output_write_failed";
   if(total_mode_cases==0) { error="no_mode_cases"; return false; }
   return ok && flushed && !IsStopped();
}
bool ManifestRow(const int h,const string key,const string value)
{
   string line=""; Cell(line,key); Cell(line,value);
   return WriteLine(h,line);
}
void Manifest(const bool computed,const int requested,const int completed,const string error)
{
   int h=OutputFile("manifest.csv");
   if(h==INVALID_HANDLE) return;
   bool ok=WriteLine(h,"key,value");
   ok=ok && ManifestRow(h,"schema","vortex.native.parity-result.v1");
   ok=ok && ManifestRow(h,"fixture_kind",FIXTURE_KIND);
   ok=ok && ManifestRow(h,"harness_version",HARNESS_VERSION);
   ok=ok && ManifestRow(h,"core_version",VORTEX_NATIVE_CORE_VERSION);
   ok=ok && ManifestRow(h,"status",computed && !output_failed ? "COMPUTED_FOR_COMPARISON" : "FAILED");
   ok=ok && ManifestRow(h,"cases_requested",IntText(requested));
   ok=ok && ManifestRow(h,"cases_completed",IntText(completed));
   ok=ok && ManifestRow(h,"signal_rows",IntText(total_signal_rows));
   ok=ok && ManifestRow(h,"mode_cases",IntText(total_mode_cases));
   ok=ok && ManifestRow(h,"mode_results",IntText(total_mode_results));
   ok=ok && ManifestRow(h,"error",error);
   ok=ok && ManifestRow(h,"parity_evaluated","false");
   ok=ok && ManifestRow(h,"strategy_approval","false");
   FinishFile(h);
}
void OnStart()
{
   if(!EnableOfflineParity) { Print("Offline parity harness disabled; no files opened."); return; }
   if(!SafeName(FixtureDirectory)) { Print("Offline parity refused: unsafe fixture folder."); return; }
   string error="";
   int marker=InputFile("fixture_kind.txt",error);
   if(marker==INVALID_HANDLE) { Print("Offline parity refused: fixture marker unavailable."); return; }
   bool synthetic=Header(marker,FIXTURE_KIND,error);
   FileClose(marker);
   if(!synthetic) { Print("Offline parity refused: explicit synthetic fixture marker required."); return; }
   string cases[];
   if(!LoadCases(cases,error)) { Print("Offline parity refused: ",error); return; }
   result_folder="VortexParityResult_"+StringFormat("%I64u",GetTickCount64());
   if(!FolderCreate(result_folder)) { Print("Offline parity cannot create new output folder."); return; }
   int completed=0;
   bool ok=true;
   for(int i=0;ok && i<ArraySize(cases) && !IsStopped();++i)
   {
      MqlRates m5[],m15[],h1[]; VxExternal external[]; VxSignal result[];
      ok=LoadRates(cases[i]+"_M5.csv",m5,error) && LoadRates(cases[i]+"_M15.csv",m15,error) &&
         LoadRates(cases[i]+"_H1.csv",h1,error) && LoadExternal(cases[i]+"_external.csv",external,error);
      if(ok) ok=VxBuildSignals(m5,m15,h1,external,result,error);
      if(ok && ArraySize(result)!=ArraySize(m5)) { error="kernel_output_count_mismatch"; ok=false; }
      if(ok) ok=SaveSignals(cases[i],result,error);
      if(ok) ++completed;
   }
   if(ok && !IsStopped()) ok=ModeCases(error);
   if(IsStopped()) { ok=false; error="interrupted"; }
   if(output_failed) { ok=false; error="output_write_failed"; }
   Manifest(ok,ArraySize(cases),completed,error);
   Print(ok && !output_failed ? "SYNTHETIC OFFLINE results computed; Python comparison still required. " :
                               "SYNTHETIC OFFLINE run FAILED; results incomplete. ",result_folder);
}
