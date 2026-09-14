// One-shot PRIVATE broker-reported account evidence. No trading operations.
#property strict
#property script_show_inputs
#property version "1.00"
#property description "Private DEMO account evidence; disabled by default; no orders."

input bool EnableExport=false;
input long ExpectedDemoLogin=0; // Runtime input only; never commit an account ID.
const int MAX_DEALS=100000;     // Oversized history is INVALID, never truncated silently.

struct AccountSnapshot
{
   double balance,equity,profit,credit,margin,free_margin;
   long leverage,positions,orders;
};

bool Identity()
{
   ResetLastError();
   bool ok=(ExpectedDemoLogin>0 && !MQLInfoInteger(MQL_TESTER) &&
      TerminalInfoInteger(TERMINAL_CONNECTED) &&
      AccountInfoInteger(ACCOUNT_LOGIN)==ExpectedDemoLogin &&
      AccountInfoInteger(ACCOUNT_TRADE_MODE)==ACCOUNT_TRADE_MODE_DEMO &&
      AccountInfoInteger(ACCOUNT_MARGIN_MODE)==ACCOUNT_MARGIN_MODE_RETAIL_HEDGING &&
      AccountInfoString(ACCOUNT_CURRENCY)=="USD");
   return(ok && GetLastError()==0);
}

bool AD(const ENUM_ACCOUNT_INFO_DOUBLE property,double &value)
{
   ResetLastError(); value=AccountInfoDouble(property);
   return(GetLastError()==0 && MathIsValidNumber(value));
}

bool Snapshot(AccountSnapshot &a)
{
   if(!Identity()) return false;
   if(!AD(ACCOUNT_BALANCE,a.balance) || !AD(ACCOUNT_EQUITY,a.equity) ||
      !AD(ACCOUNT_PROFIT,a.profit) || !AD(ACCOUNT_CREDIT,a.credit) ||
      !AD(ACCOUNT_MARGIN,a.margin) || !AD(ACCOUNT_MARGIN_FREE,a.free_margin)) return false;
   ResetLastError();
   a.leverage=AccountInfoInteger(ACCOUNT_LEVERAGE);
   a.positions=PositionsTotal(); a.orders=OrdersTotal();
   return(GetLastError()==0 && a.leverage>0 && a.margin>=0 && a.positions>=0 && a.orders>=0 && Identity());
}

bool Same(const AccountSnapshot &a,const AccountSnapshot &b)
{
   return(MathAbs(a.balance-b.balance)<1e-8 && MathAbs(a.equity-b.equity)<1e-8 &&
      MathAbs(a.profit-b.profit)<1e-8 && MathAbs(a.credit-b.credit)<1e-8 &&
      MathAbs(a.margin-b.margin)<1e-8 && MathAbs(a.free_margin-b.free_margin)<1e-8 &&
      a.leverage==b.leverage && a.positions==b.positions && a.orders==b.orders);
}

string Q(string text)
{
   StringReplace(text,"\"","\"\""); return "\""+text+"\"";
}
string N(double value) { return DoubleToString(value,16); }
string T(datetime value)
{
   string text=TimeToString(value,TIME_DATE|TIME_SECONDS);
   StringReplace(text,".","-"); StringReplace(text," ","T"); return text;
}

bool ReadDeal(ulong ticket,const datetime through_time,string &row,bool &supported)
{
   ENUM_DEAL_PROPERTY_INTEGER ip[]={DEAL_ORDER,DEAL_POSITION_ID,DEAL_TIME,
      DEAL_TIME_MSC,DEAL_TYPE,DEAL_ENTRY,DEAL_REASON,DEAL_MAGIC};
   ENUM_DEAL_PROPERTY_DOUBLE dp[]={DEAL_VOLUME,DEAL_PRICE,DEAL_COMMISSION,
      DEAL_SWAP,DEAL_PROFIT,DEAL_FEE,DEAL_SL,DEAL_TP};
   ENUM_DEAL_PROPERTY_STRING sp[]={DEAL_SYMBOL,DEAL_COMMENT,DEAL_EXTERNAL_ID};
   long iv[8]; double dv[8]; string sv[3];
   for(int i=0;i<8;i++)
   {
      ResetLastError();
      if(!HistoryDealGetInteger(ticket,ip[i],iv[i]) || GetLastError()!=0) return false;
      ResetLastError();
      if(!HistoryDealGetDouble(ticket,dp[i],dv[i]) || GetLastError()!=0 || !MathIsValidNumber(dv[i])) return false;
   }
   for(int i=0;i<3;i++)
   {
      ResetLastError();
      if(!HistoryDealGetString(ticket,sp[i],sv[i]) || GetLastError()!=0) return false;
   }
   bool known=(iv[0]>=0 && iv[1]>=0 && iv[2]>=0 && iv[2]<=(long)through_time && iv[3]>=0 &&
      iv[4]>=DEAL_TYPE_BUY && iv[4]<=DEAL_TAX &&
      iv[5]>=DEAL_ENTRY_IN && iv[5]<=DEAL_ENTRY_OUT_BY &&
      iv[6]>=DEAL_REASON_CLIENT && iv[6]<=DEAL_REASON_CORPORATE_ACTION &&
      dv[0]>=0 && dv[1]>=0 && dv[6]>=0 && dv[7]>=0);
   bool trade=(iv[4]==DEAL_TYPE_BUY || iv[4]==DEAL_TYPE_SELL);
   supported=(known && (trade || iv[4]==DEAL_TYPE_BALANCE) &&
      (!trade || (iv[5]==DEAL_ENTRY_IN || iv[5]==DEAL_ENTRY_OUT)));
   // Raw fields are retained even for a known unsupported accounting type.
   row=StringFormat("%I64u",ticket);
   for(int i=0;i<8;i++) row+=","+IntegerToString(iv[i]);
   row+=","+Q(T((datetime)iv[2]))+","+Q(EnumToString((ENUM_DEAL_TYPE)iv[4]))+
        ","+Q(EnumToString((ENUM_DEAL_ENTRY)iv[5]))+","+Q(EnumToString((ENUM_DEAL_REASON)iv[6]));
   for(int i=0;i<8;i++) row+=","+N(dv[i]);
   for(int i=0;i<3;i++) row+=","+Q(sv[i]);
   row+=","+(supported?"true":"false");
   return true;
}

bool WriteUtf8(const int handle,const string value)
{
   uchar bytes[];
   ResetLastError();
   int count=StringToCharArray(value,bytes,0,WHOLE_ARRAY,CP_UTF8);
   if(count<=1 || GetLastError()!=0 || bytes[count-1]!=0) return false;
   // uchar is one byte. Exclude the terminal NUL, require the exact byte count.
   int expected=count-1;
   ResetLastError(); uint written=FileWriteArray(handle,bytes,0,expected);
   return(written==(uint)expected && GetLastError()==0);
}

bool WriteText(const string path,const string value)
{
   if(!Identity()) return false;
   ResetLastError();
   int h=FileOpen(path,FILE_WRITE|FILE_BIN);
   if(h==INVALID_HANDLE) return false;
   bool ok=WriteUtf8(h,value);
   ResetLastError(); FileFlush(h); ok=(ok && GetLastError()==0);
   ResetLastError(); FileClose(h); return(ok && GetLastError()==0);
}

bool WriteDeals(const string path,const string &rows[])
{
   if(!Identity()) return false;
   ResetLastError();
   int h=FileOpen(path,FILE_WRITE|FILE_BIN);
   if(h==INVALID_HANDLE) return false;
   string header="deal_ticket,order_ticket,position_id,time_epoch_seconds,time_msc,type_code,entry_code,reason_code,magic,time_server,type_name,entry_name,reason_name,volume,price,commission,swap,profit,fee,sl,tp,symbol,comment,external_id,accounting_type_supported\r\n";
   bool ok=WriteUtf8(h,header);
   for(int i=0;i<ArraySize(rows) && ok;i++)
   {
      if(IsStopped() || !Identity()) { ok=false; break; }
      ok=WriteUtf8(h,rows[i]+"\r\n");
   }
   ResetLastError(); FileFlush(h); ok=(ok && GetLastError()==0);
   ResetLastError(); FileClose(h); return(ok && GetLastError()==0);
}

void Invalid(const string folder,const datetime through_time,const string why,
             const bool selected,const int select_error,const int count)
{
   // An identity failure permits no further file writes, even a redacted marker.
   if(Identity())
   {
      string manifest="{\n  \"schemaVersion\":1,\n  \"status\":\"INVALID\",\n  \"reason\":\""+why+"\",\n"+
         "  \"privateOnly\":true,\n  \"dataWrittenCompletely\":false,\n  \"requestedFromEpochSeconds\":0,\n"+
         "  \"requestedThroughEpochSeconds\":"+IntegerToString((long)through_time)+",\n"+
         "  \"timeBasis\":\"broker_server_time_offset_unverified\",\n  \"historySelectSucceeded\":"+(selected?"true":"false")+",\n"+
         "  \"historySelectError\":"+IntegerToString(select_error)+",\n  \"returnedDealCount\":"+(count<0?"null":IntegerToString(count))+",\n"+
         "  \"independentHistoryCompleteness\":\"NOT_PROVEN\",\n  \"baselineGo\":false\n}\n";
      // Separate filename avoids overwriting or blessing an unfinished data manifest.
      if(WriteText(folder+"\\invalid.part",manifest) && Identity())
         FileMove(folder+"\\invalid.part",0,folder+"\\INVALID.json",0);
   }
   Print("VORTEX account evidence INVALID: "+why+".");
}

void OnStart()
{
   if(!EnableExport || ExpectedDemoLogin<=0)
   { Print("VORTEX account evidence DISABLED; no export requested."); return; }
   AccountSnapshot before,after,commit;
   if(!Snapshot(before))
   { Print("VORTEX account evidence INVALID: identity_or_account_unavailable."); return; }
   datetime from_time=0,through_time=TimeTradeServer();
   if(through_time<=0)
   { Print("VORTEX account evidence INVALID: server_time_unavailable."); return; }
   string root="VortexAccountEvidence";
   FolderCreate(root);
   string folder=root+"\\"+IntegerToString((long)through_time)+"_"+
      IntegerToString((long)GetTickCount64())+"_"+IntegerToString((long)GetMicrosecondCount());
   ResetLastError();
   if(!FolderCreate(folder))
   { Print("VORTEX account evidence INVALID: unique_folder_creation_failed."); return; }
   ResetLastError();
   bool selected=HistorySelect(from_time,through_time); int select_error=GetLastError();
   if(!selected || select_error!=0)
   { Invalid(folder,through_time,"history_select_failed",selected,select_error,-1); return; }
   ResetLastError(); int count=HistoryDealsTotal(); int count_error=GetLastError();
   if(count_error!=0 || count<0 || count>MAX_DEALS)
   { Invalid(folder,through_time,"history_count_unavailable_or_over_limit",true,0,count_error==0?count:-1); return; }
   string rows[];
   if(ArrayResize(rows,count)!=count)
   { Invalid(folder,through_time,"allocation_failed",true,0,count); return; }
   int unsupported=0;
   for(int i=0;i<count;i++)
   {
      if(IsStopped() || !Identity())
      { Invalid(folder,through_time,"interrupted_or_identity_changed",true,0,count); return; }
      ResetLastError(); ulong ticket=HistoryDealGetTicket(i);
      bool supported=false;
      if(ticket==0 || GetLastError()!=0 || !ReadDeal(ticket,through_time,rows[i],supported))
      { Invalid(folder,through_time,"deal_property_unavailable",true,0,count); return; }
      if(!supported) unsupported++;
   }
   if(!Snapshot(after) || !Same(before,after))
   { Invalid(folder,through_time,"account_changed_during_read",true,0,count); return; }

   // Unique folder; never overwrite prior evidence. Final manifest is the commit marker.
   string account="currency,account_mode,margin_mode,balance,equity,profit,credit,margin,free_margin,leverage,open_positions,pending_orders\r\n"+
      "USD,DEMO,HEDGE,"+N(before.balance)+","+N(before.equity)+","+N(before.profit)+","+N(before.credit)+","+
      N(before.margin)+","+N(before.free_margin)+","+IntegerToString(before.leverage)+","+
      IntegerToString(before.positions)+","+IntegerToString(before.orders)+"\r\n";
   if(!Snapshot(commit) || !Same(before,commit) || !WriteDeals(folder+"\\deals.part",rows) ||
      !WriteText(folder+"\\account.part",account) || !Snapshot(commit) || !Same(before,commit))
   { Invalid(folder,through_time,"write_or_account_recheck_failed",true,0,count); return; }
   bool valid=(count>0 && unsupported==0 && before.credit==0);
   string why=(count==0?"empty_broker_history":unsupported>0?"unsupported_accounting_values":before.credit!=0?"nonzero_credit":"capture_checks_passed");
   string manifest="{\n  \"schemaVersion\":1,\n  \"status\":\""+(valid?"VALID_CAPTURE":"INVALID")+"\",\n"+
      "  \"reason\":\""+why+"\",\n  \"privateOnly\":true,\n  \"demoUsdHedgeIdentityVerified\":true,\n"+
      "  \"dataWrittenCompletely\":true,\n"+
      "  \"timeBasis\":\"broker_server_time_offset_unverified\",\n  \"requestedFromEpochSeconds\":"+IntegerToString((long)from_time)+",\n"+
      "  \"requestedThroughEpochSeconds\":"+IntegerToString((long)through_time)+",\n  \"requestedThroughServer\":\""+T(through_time)+"\",\n"+
      "  \"historySelectSucceeded\":true,\n  \"historySelectError\":0,\n  \"returnedDealCount\":"+IntegerToString(count)+",\n"+
      "  \"writtenDealCount\":"+IntegerToString(ArraySize(rows))+",\n  \"unsupportedDealCount\":"+IntegerToString(unsupported)+",\n"+
      "  \"accountStableAcrossReadAndWrite\":true,\n  \"terminalBuild\":"+IntegerToString(TerminalInfoInteger(TERMINAL_BUILD))+",\n"+
      "  \"independentHistoryCompleteness\":\"NOT_PROVEN\",\n  \"atomicBrokerSnapshot\":false,\n"+
      "  \"dailyEquityDrawdown\":null,\n  \"capitalOrCostsApproved\":false,\n  \"baselineGo\":false\n}\n";
   if(!WriteText(folder+"\\manifest.part",manifest) || !Snapshot(commit) || !Same(before,commit) ||
      !FileMove(folder+"\\deals.part",0,folder+"\\deals.csv",0) ||
      !FileMove(folder+"\\account.part",0,folder+"\\account.csv",0) ||
      !Snapshot(commit) || !Same(before,commit) || !FileMove(folder+"\\manifest.part",0,folder+"\\manifest.json",0))
   { Invalid(folder,through_time,"commit_failed",true,0,count); return; }
   Print("VORTEX private account evidence "+(valid?"VALID_CAPTURE":"INVALID")+": "+why+". Files stay in terminal MQL5/Files/VortexAccountEvidence.");
}
