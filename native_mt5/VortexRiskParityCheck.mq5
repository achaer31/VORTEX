// SYNTHETIC OFFLINE RISK ONLY. No account, authentication, quotes, or orders.
#property strict
#property version "1.00"
#property description "Disabled-by-default independent native risk comparison harness."
#property script_show_inputs
#include "VortexRiskCore.mqh"
input bool EnableOfflineRiskParity=false;
input string FixtureDirectory="VortexRiskFixtures";
const string HARNESS_VERSION="VORTEX-NATIVE-RISK-PARITY-0.1";
const string FIXTURE_KIND="SYNTHETIC_OFFLINE_RISK_V1";
const int MAX_RISK_CASES=512;
string result_folder="";
bool output_failed=false;
long family_cases[4],family_results[4];
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
string FloatText(const double value) { return VxrFinite(value) ? DoubleToString(value,16) : ""; }
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
   return VxrFinite(value);
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

bool IntField(const string text,int &value)
{
   long parsed=0;
   if(!IntegerValue(text,parsed) || parsed < -2147483647 || parsed > 2147483647) return false;
   value=(int)parsed; return true;
}
bool EnumField(const string text,string &value)
{
   if(!SafeName(text)) return false;
   value=text; return true;
}
bool NewCase(const string name,string &ids[],string &error)
{
   int n=ArraySize(ids);
   if(!SafeName(name) || n>=MAX_RISK_CASES) { error="invalid_case_id_or_count"; return false; }
   for(int i=0;i<n;i++) if(ids[i]==name) { error="duplicate_case_id"; return false; }
   if(ArrayResize(ids,n+1)!=n+1) { error="case_memory_failed"; return false; }
   ids[n]=name; return true;
}

bool RunSize(string &error)
{
   int source=InputFile("risk_size_cases.csv",error);
   if(source==INVALID_HANDLE) return false;
   bool ok=Header(source,"case_id,metadata_valid,loss_estimate_valid,margin_estimate_valid,side,digits,equity,risk_fraction,max_risk_fraction,entry,stop,lot_min,lot_step,lot_max,tick_size,min_stop_distance,free_margin,max_margin_fraction,loss_per_lot,cost_reserve_per_lot,margin_per_lot",error);
   int target=OutputFile("risk_size_results.csv");
   if(target==INVALID_HANDLE) { FileClose(source); error="output_open_failed"; return false; }
   ok=ok && WriteLine(target,"case_id,allowed,reason,mode,exit_policy,lots,risk_cash,margin,budget,minimum_risk,stop,risk_fraction,tp1_lots,tp2_lots,runner_lots,campaign_nominal_after,campaign_open_risk_after,add_level,stress_only,execution_authorized");
   string ids[];
   while(ok && !FileIsEnding(source) && !IsStopped())
   {
      string line=FileReadString(source),cells[];
      if(line=="" && FileIsEnding(source)) break;
      if(!Fields(line,21,cells,error) || !NewCase(cells[0],ids,error)) { ok=false; break; }
      VxrSizingFacts row; VxrResetSizing(row); VxrPlan result;
      ok=Flag(cells[1],row.metadataValid) &&
         Flag(cells[2],row.lossEstimateValid) &&
         Flag(cells[3],row.marginEstimateValid) &&
         IntField(cells[4],row.side) &&
         IntField(cells[5],row.digits) &&
         Numeric(cells[6],false,row.equity) &&
         Numeric(cells[7],false,row.riskFraction) &&
         Numeric(cells[8],false,row.maxRiskFraction) &&
         Numeric(cells[9],false,row.entry) &&
         Numeric(cells[10],false,row.stop) &&
         Numeric(cells[11],false,row.lotMin) &&
         Numeric(cells[12],false,row.lotStep) &&
         Numeric(cells[13],false,row.lotMax) &&
         Numeric(cells[14],false,row.tickSize) &&
         Numeric(cells[15],false,row.minStopDistance) &&
         Numeric(cells[16],false,row.freeMargin) &&
         Numeric(cells[17],false,row.maxMarginFraction) &&
         Numeric(cells[18],false,row.lossPerLot) &&
         Numeric(cells[19],false,row.costReservePerLot) &&
         Numeric(cells[20],false,row.marginPerLot);
      if(!ok) { error="invalid_risk_fixture_field"; break; }
      ++family_cases[0];
      bool accepted=VxrSize(row,result);
      if(accepted!=result.allowed) { error="kernel_allowed_mismatch"; ok=false; break; }
      string rendered=""; Cell(rendered,cells[0]);
      Cell(rendered,BoolText(result.allowed));
      Cell(rendered,result.reason);
      Cell(rendered,result.mode);
      Cell(rendered,result.exitPolicy);
      Cell(rendered,FloatText(result.lots));
      Cell(rendered,FloatText(result.riskCash));
      Cell(rendered,FloatText(result.margin));
      Cell(rendered,FloatText(result.budget));
      Cell(rendered,FloatText(result.minimumRisk));
      Cell(rendered,FloatText(result.stop));
      Cell(rendered,FloatText(result.riskFraction));
      Cell(rendered,FloatText(result.tp1Lots));
      Cell(rendered,FloatText(result.tp2Lots));
      Cell(rendered,FloatText(result.runnerLots));
      Cell(rendered,FloatText(result.campaignNominalAfter));
      Cell(rendered,FloatText(result.campaignOpenRiskAfter));
      Cell(rendered,IntText(result.addLevel));
      Cell(rendered,BoolText(result.stressOnly));
      Cell(rendered,BoolText(result.executionAuthorized));
      ok=WriteLine(target,rendered);
      if(ok) ++family_results[0];
   }
   FileClose(source);
   bool flushed=FinishFile(target);
   if(!flushed) error="output_write_failed";
   if(family_cases[0]==0) { error="no_risk_cases"; return false; }
   return ok && flushed && !IsStopped();
}

bool RunGate(string &error)
{
   int source=InputFile("risk_gate_cases.csv",error);
   if(source==INVALID_HANDLE) return false;
   bool ok=Header(source,"case_id,day_start_equity,equity,loss_streak,requested_mode,connected,data_fresh,protection_confirmed",error);
   int target=OutputFile("risk_gate_results.csv");
   if(target==INVALID_HANDLE) { FileClose(source); error="output_open_failed"; return false; }
   ok=ok && WriteLine(target,"case_id,mode,reason,risk_fraction,drawdown");
   string ids[];
   while(ok && !FileIsEnding(source) && !IsStopped())
   {
      string line=FileReadString(source),cells[];
      if(line=="" && FileIsEnding(source)) break;
      if(!Fields(line,8,cells,error) || !NewCase(cells[0],ids,error)) { ok=false; break; }
      VxrGate result;
      double dayStartEquity=0;
      double equity=0;
      int lossStreak=0;
      string requestedMode="";
      bool connected=false;
      bool dataFresh=false;
      bool protectiveOrdersConfirmed=false;
      ok=Numeric(cells[1],false,dayStartEquity) &&
         Numeric(cells[2],false,equity) &&
         IntField(cells[3],lossStreak) &&
         EnumField(cells[4],requestedMode) &&
         Flag(cells[5],connected) &&
         Flag(cells[6],dataFresh) &&
         Flag(cells[7],protectiveOrdersConfirmed);
      if(!ok) { error="invalid_risk_fixture_field"; break; }
      ++family_cases[1];
      VxrModeGate(dayStartEquity,equity,lossStreak,requestedMode,connected,dataFresh,protectiveOrdersConfirmed,result);
      string rendered=""; Cell(rendered,cells[0]);
      Cell(rendered,result.mode);
      Cell(rendered,result.reason);
      Cell(rendered,FloatText(result.riskFraction));
      Cell(rendered,FloatText(result.drawdown));
      ok=WriteLine(target,rendered);
      if(ok) ++family_results[1];
   }
   FileClose(source);
   bool flushed=FinishFile(target);
   if(!flushed) error="output_write_failed";
   if(family_cases[1]==0) { error="no_risk_cases"; return false; }
   return ok && flushed && !IsStopped();
}

bool RunCampaign(string &error)
{
   int source=InputFile("risk_campaign_cases.csv",error);
   if(source==INVALID_HANDLE) return false;
   bool ok=Header(source,"case_id,metadata_valid,loss_estimate_valid,margin_estimate_valid,side,digits,equity,risk_fraction,max_risk_fraction,entry,stop,lot_min,lot_step,lot_max,tick_size,min_stop_distance,free_margin,max_margin_fraction,loss_per_lot,cost_reserve_per_lot,margin_per_lot,day_start_equity,loss_streak,requested_mode,profile,connected,data_fresh,protection_confirmed,persistent_frozen,daily_killed,extreme_disabled,capital_valid,reconciled,ownership_valid,pending_intent,signal_ready,news_valid,news_blocked,macro_valid,session_valid,quote_fresh,decision_fresh,research_stress_permitted,campaign_count,adds,campaign_side,base_open,base_breakeven_confirmed,earlier_breakeven_confirmed,all_legs_profitable,campaign_starting_equity,campaign_nominal_risk,current_open_risk,closed_gain_r,consensus,orion,nova,current_risk_valid,atr_m15,liquidation_price,spread_price,used_margin,margin_allocation_valid",error);
   int target=OutputFile("risk_campaign_results.csv");
   if(target==INVALID_HANDLE) { FileClose(source); error="output_open_failed"; return false; }
   ok=ok && WriteLine(target,"case_id,allowed,reason,mode,exit_policy,lots,risk_cash,margin,budget,minimum_risk,stop,risk_fraction,tp1_lots,tp2_lots,runner_lots,campaign_nominal_after,campaign_open_risk_after,add_level,stress_only,execution_authorized");
   string ids[];
   while(ok && !FileIsEnding(source) && !IsStopped())
   {
      string line=FileReadString(source),cells[];
      if(line=="" && FileIsEnding(source)) break;
      if(!Fields(line,63,cells,error) || !NewCase(cells[0],ids,error)) { ok=false; break; }
      VxrCampaignFacts row; VxrResetCampaign(row); VxrPlan result;
      ok=Flag(cells[1],row.sizing.metadataValid) &&
         Flag(cells[2],row.sizing.lossEstimateValid) &&
         Flag(cells[3],row.sizing.marginEstimateValid) &&
         IntField(cells[4],row.sizing.side) &&
         IntField(cells[5],row.sizing.digits) &&
         Numeric(cells[6],false,row.sizing.equity) &&
         Numeric(cells[7],false,row.sizing.riskFraction) &&
         Numeric(cells[8],false,row.sizing.maxRiskFraction) &&
         Numeric(cells[9],false,row.sizing.entry) &&
         Numeric(cells[10],false,row.sizing.stop) &&
         Numeric(cells[11],false,row.sizing.lotMin) &&
         Numeric(cells[12],false,row.sizing.lotStep) &&
         Numeric(cells[13],false,row.sizing.lotMax) &&
         Numeric(cells[14],false,row.sizing.tickSize) &&
         Numeric(cells[15],false,row.sizing.minStopDistance) &&
         Numeric(cells[16],false,row.sizing.freeMargin) &&
         Numeric(cells[17],false,row.sizing.maxMarginFraction) &&
         Numeric(cells[18],false,row.sizing.lossPerLot) &&
         Numeric(cells[19],false,row.sizing.costReservePerLot) &&
         Numeric(cells[20],false,row.sizing.marginPerLot) &&
         Numeric(cells[21],false,row.dayStartEquity) &&
         IntField(cells[22],row.lossStreak) &&
         EnumField(cells[23],row.requestedMode) &&
         EnumField(cells[24],row.profile) &&
         Flag(cells[25],row.connected) &&
         Flag(cells[26],row.dataFresh) &&
         Flag(cells[27],row.protectiveOrdersConfirmed) &&
         Flag(cells[28],row.persistentFrozen) &&
         Flag(cells[29],row.dailyKilled) &&
         Flag(cells[30],row.extremeDisabled) &&
         Flag(cells[31],row.capitalValid) &&
         Flag(cells[32],row.reconciled) &&
         Flag(cells[33],row.ownershipValid) &&
         Flag(cells[34],row.pendingIntent) &&
         Flag(cells[35],row.signalReady) &&
         Flag(cells[36],row.newsValid) &&
         Flag(cells[37],row.newsBlocked) &&
         Flag(cells[38],row.macroValid) &&
         Flag(cells[39],row.sessionValid) &&
         Flag(cells[40],row.quoteFresh) &&
         Flag(cells[41],row.decisionFresh) &&
         Flag(cells[42],row.researchStressPermitted) &&
         IntField(cells[43],row.campaignCount) &&
         IntField(cells[44],row.adds) &&
         IntField(cells[45],row.campaignSide) &&
         Flag(cells[46],row.baseOpen) &&
         Flag(cells[47],row.baseBreakevenConfirmed) &&
         Flag(cells[48],row.allEarlierBreakevenConfirmed) &&
         Flag(cells[49],row.allLegsStrictlyProfitable) &&
         Numeric(cells[50],false,row.campaignStartingEquity) &&
         Numeric(cells[51],false,row.campaignNominalRisk) &&
         Numeric(cells[52],false,row.currentOpenRisk) &&
         Numeric(cells[53],false,row.closedGainR) &&
         Numeric(cells[54],false,row.consensus) &&
         Numeric(cells[55],false,row.orion) &&
         Numeric(cells[56],false,row.nova) &&
         Flag(cells[57],row.currentRiskValid) &&
         Numeric(cells[58],false,row.atrM15) &&
         Numeric(cells[59],false,row.liquidationPrice) &&
         Numeric(cells[60],false,row.spreadPrice) &&
         Numeric(cells[61],false,row.usedMargin) &&
         Flag(cells[62],row.marginAllocationValid);
      if(!ok) { error="invalid_risk_fixture_field"; break; }
      ++family_cases[2];
      bool accepted=VxrPlanCampaign(row,result);
      if(accepted!=result.allowed) { error="kernel_allowed_mismatch"; ok=false; break; }
      string rendered=""; Cell(rendered,cells[0]);
      Cell(rendered,BoolText(result.allowed));
      Cell(rendered,result.reason);
      Cell(rendered,result.mode);
      Cell(rendered,result.exitPolicy);
      Cell(rendered,FloatText(result.lots));
      Cell(rendered,FloatText(result.riskCash));
      Cell(rendered,FloatText(result.margin));
      Cell(rendered,FloatText(result.budget));
      Cell(rendered,FloatText(result.minimumRisk));
      Cell(rendered,FloatText(result.stop));
      Cell(rendered,FloatText(result.riskFraction));
      Cell(rendered,FloatText(result.tp1Lots));
      Cell(rendered,FloatText(result.tp2Lots));
      Cell(rendered,FloatText(result.runnerLots));
      Cell(rendered,FloatText(result.campaignNominalAfter));
      Cell(rendered,FloatText(result.campaignOpenRiskAfter));
      Cell(rendered,IntText(result.addLevel));
      Cell(rendered,BoolText(result.stressOnly));
      Cell(rendered,BoolText(result.executionAuthorized));
      ok=WriteLine(target,rendered);
      if(ok) ++family_results[2];
   }
   FileClose(source);
   bool flushed=FinishFile(target);
   if(!flushed) error="output_write_failed";
   if(family_cases[2]==0) { error="no_risk_cases"; return false; }
   return ok && flushed && !IsStopped();
}

bool RunStop(string &error)
{
   int source=InputFile("risk_stop_cases.csv",error);
   if(source==INVALID_HANDLE) return false;
   bool ok=Header(source,"case_id,entry,structural_stop,atr,side,tick_size",error);
   int target=OutputFile("risk_stop_results.csv");
   if(target==INVALID_HANDLE) { FileClose(source); error="output_open_failed"; return false; }
   ok=ok && WriteLine(target,"case_id,allowed,reason,stop");
   string ids[];
   while(ok && !FileIsEnding(source) && !IsStopped())
   {
      string line=FileReadString(source),cells[];
      if(line=="" && FileIsEnding(source)) break;
      if(!Fields(line,6,cells,error) || !NewCase(cells[0],ids,error)) { ok=false; break; }
      bool result_allowed=false; string result_reason=""; double result_stop=0;
      double entry=0;
      double structuralStop=0;
      double atr=0;
      int side=0;
      double tickSize=0;
      ok=Numeric(cells[1],false,entry) &&
         Numeric(cells[2],false,structuralStop) &&
         Numeric(cells[3],false,atr) &&
         IntField(cells[4],side) &&
         Numeric(cells[5],false,tickSize);
      if(!ok) { error="invalid_risk_fixture_field"; break; }
      ++family_cases[3];
      result_allowed=VxrPrepareStop(entry,structuralStop,atr,side,tickSize,result_stop,result_reason);
      string rendered=""; Cell(rendered,cells[0]);
      Cell(rendered,BoolText(result_allowed));
      Cell(rendered,result_reason);
      Cell(rendered,FloatText(result_stop));
      ok=WriteLine(target,rendered);
      if(ok) ++family_results[3];
   }
   FileClose(source);
   bool flushed=FinishFile(target);
   if(!flushed) error="output_write_failed";
   if(family_cases[3]==0) { error="no_risk_cases"; return false; }
   return ok && flushed && !IsStopped();
}

bool ManifestRow(const int handle,const string key,const string value)
{
   string line=""; Cell(line,key); Cell(line,value); return WriteLine(handle,line);
}
void Manifest(const bool computed,const string error)
{
   int handle=OutputFile("manifest.csv");
   if(handle==INVALID_HANDLE) return;
   bool ok=WriteLine(handle,"key,value");
   ok=ok && ManifestRow(handle,"schema","vortex.native.risk-result.v1");
   ok=ok && ManifestRow(handle,"fixture_kind",FIXTURE_KIND);
   ok=ok && ManifestRow(handle,"harness_version",HARNESS_VERSION);
   ok=ok && ManifestRow(handle,"core_version",VORTEX_NATIVE_RISK_VERSION);
   ok=ok && ManifestRow(handle,"status",computed && !output_failed ? "COMPUTED_FOR_COMPARISON" : "FAILED");
   ok=ok && ManifestRow(handle,"size_cases",IntText(family_cases[0]));
   ok=ok && ManifestRow(handle,"size_results",IntText(family_results[0]));
   ok=ok && ManifestRow(handle,"gate_cases",IntText(family_cases[1]));
   ok=ok && ManifestRow(handle,"gate_results",IntText(family_results[1]));
   ok=ok && ManifestRow(handle,"campaign_cases",IntText(family_cases[2]));
   ok=ok && ManifestRow(handle,"campaign_results",IntText(family_results[2]));
   ok=ok && ManifestRow(handle,"stop_cases",IntText(family_cases[3]));
   ok=ok && ManifestRow(handle,"stop_results",IntText(family_results[3]));
   ok=ok && ManifestRow(handle,"error",error);
   ok=ok && ManifestRow(handle,"parity_evaluated","false");
   ok=ok && ManifestRow(handle,"strategy_approval","false");
   ok=ok && ManifestRow(handle,"execution_authorized","false");
   FinishFile(handle);
}
void OnStart()
{
   if(!EnableOfflineRiskParity) { Print("Offline risk harness disabled; no files opened."); return; }
   if(!SafeName(FixtureDirectory)) { Print("Offline risk refused: unsafe fixture folder."); return; }
   string error="";
   int marker=InputFile("fixture_kind.txt",error);
   if(marker==INVALID_HANDLE) { Print("Offline risk refused: fixture marker unavailable."); return; }
   bool synthetic=Header(marker,FIXTURE_KIND,error) && FileIsEnding(marker);
   FileClose(marker);
   if(!synthetic) { Print("Offline risk refused: explicit synthetic fixture marker required."); return; }
   result_folder="VortexRiskParityResult_"+StringFormat("%I64u",GetTickCount64());
   if(!FolderCreate(result_folder)) { Print("Offline risk cannot create new output folder."); return; }
   bool ok=RunSize(error) && RunGate(error) && RunCampaign(error) && RunStop(error);
   if(IsStopped()) { ok=false; error="interrupted"; }
   if(output_failed) { ok=false; error="output_write_failed"; }
   Manifest(ok,error);
   Print(ok && !output_failed ? "SYNTHETIC OFFLINE risk results computed; independent comparison required. " :
                               "SYNTHETIC OFFLINE risk run FAILED. ",result_folder);
}
