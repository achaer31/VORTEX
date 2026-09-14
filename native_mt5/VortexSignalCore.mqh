// Pure deterministic port of frozen research_v02/vortex_v02/{data,engines}.py.
// No terminal, broker, file, order, network, clock, or indicator-handle calls.
// Caller supplies ascending, completed UTC-labelled bars and point-in-time context.
#ifndef VORTEX_SIGNAL_CORE_MQH
#define VORTEX_SIGNAL_CORE_MQH
#define VORTEX_NATIVE_CORE_VERSION "v0.2-parity-1"

struct VxExternal
{
   datetime decisionTime;
   bool newsValid,newsBlocked,macroValid,sessionValid,sessionIdeal;
   double dxyRoc,us10yChange;
   double asiaHigh,asiaLow,londonHigh,londonLow,newyorkHigh,newyorkLow;
};
struct VxSignal
{
   datetime barOpen,decisionTime,m15ClosedAt,h1ClosedAt,h4ClosedAt;
   double orion,vortex,nova,luna,kira,atlas,consensus,atr;
   double stopLong,stopShort,swingLow,swingHigh;
   string orionReason,vortexReason,novaReason,lunaReason,kiraReason,atlasReason,mode;
   int signal,h1Alignment,h4Alignment;
   bool m15Fresh,h1Fresh,h4Fresh,executionValid,ready;
};
struct VxFeature
{
   double ema20,ema50,ema200,atr,rsi,macdHist,rocPrice;
   double priorHigh,priorLow,priorVolume,atrBaseline,trendScore;
   double pivotHigh,pivotLow,swingHigh,swingLow;
   int alignment;
};

bool VxValid(const double value)
{ return(value!=EMPTY_VALUE && MathIsValidNumber(value)); }
double VxClip(const double value)
{ return(VxValid(value)?MathMax(-100.0,MathMin(100.0,value)):EMPTY_VALUE); }
int VxSign(const double value)
{ return(value>0?1:value<0?-1:0); }
double VxEma(const double previous,const double value,const int period)
{
   // pandas ewm(adjust=False) starts from the first observation, not an SMA.
   // Its constant-observation shortcut also avoids artificial flat-price drift.
   if(previous==value) return previous;
   double alpha=2.0/(period+1.0);
   return((1.0-alpha)*previous+alpha*value);
}
double VxWilderNext(const double previous,const double value)
{
   if(previous==value) return previous;
   double alpha=1.0/14.0;
   return((1.0-alpha)*previous+alpha*value);
}
void VxResetExternal(VxExternal &value)
{
   value.decisionTime=0;
   value.newsValid=false; value.newsBlocked=true; value.macroValid=false;
   value.sessionValid=false; value.sessionIdeal=false;
   value.dxyRoc=EMPTY_VALUE; value.us10yChange=EMPTY_VALUE;
   value.asiaHigh=EMPTY_VALUE; value.asiaLow=EMPTY_VALUE;
   value.londonHigh=EMPTY_VALUE; value.londonLow=EMPTY_VALUE;
   value.newyorkHigh=EMPTY_VALUE; value.newyorkLow=EMPTY_VALUE;
}
void VxResetFeature(VxFeature &value)
{
   value.ema20=EMPTY_VALUE; value.ema50=EMPTY_VALUE; value.ema200=EMPTY_VALUE;
   value.atr=EMPTY_VALUE; value.rsi=EMPTY_VALUE; value.macdHist=EMPTY_VALUE;
   value.rocPrice=EMPTY_VALUE; value.priorHigh=EMPTY_VALUE; value.priorLow=EMPTY_VALUE;
   value.priorVolume=EMPTY_VALUE; value.atrBaseline=EMPTY_VALUE; value.trendScore=EMPTY_VALUE;
   value.pivotHigh=EMPTY_VALUE; value.pivotLow=EMPTY_VALUE;
   value.swingHigh=EMPTY_VALUE; value.swingLow=EMPTY_VALUE; value.alignment=0;
}
void VxResetSignal(VxSignal &value)
{
   value.barOpen=0; value.decisionTime=0;
   value.m15ClosedAt=0; value.h1ClosedAt=0; value.h4ClosedAt=0;
   value.orion=EMPTY_VALUE; value.vortex=EMPTY_VALUE; value.nova=EMPTY_VALUE;
   value.luna=EMPTY_VALUE; value.kira=EMPTY_VALUE; value.atlas=EMPTY_VALUE;
   value.consensus=EMPTY_VALUE; value.atr=EMPTY_VALUE;
   value.stopLong=EMPTY_VALUE; value.stopShort=EMPTY_VALUE;
   value.swingLow=EMPTY_VALUE; value.swingHigh=EMPTY_VALUE;
   value.orionReason="trend_warmup"; value.vortexReason="momentum_warmup";
   value.novaReason="structure_warmup"; value.lunaReason="sweep_warmup";
   value.kiraReason="volatility_baseline_invalid"; value.atlasReason="calendar_invalid";
   value.mode="FROZEN"; value.signal=0; value.h1Alignment=0; value.h4Alignment=0;
   value.m15Fresh=false; value.h1Fresh=false; value.h4Fresh=false;
   value.executionValid=false; value.ready=false;
}
bool VxValidateRates(const MqlRates &rates[],const int seconds,string &error)
{
   int size=ArraySize(rates);
   if(size==0) { error="empty_timeframe"; return false; }
   for(int i=0;i<size;i++)
   {
      const MqlRates bar=rates[i];
      if((long)bar.time<0 || (long)bar.time>LONG_MAX-seconds || (long)bar.time%seconds!=0 ||
         (i>0 && bar.time<=rates[i-1].time) ||
         !VxValid(bar.open) || !VxValid(bar.high) || !VxValid(bar.low) || !VxValid(bar.close) ||
         bar.open<=0 || bar.close<=0 || bar.low<=0 ||
         bar.low>MathMin(bar.open,bar.close) || bar.high<MathMax(bar.open,bar.close) ||
         bar.tick_volume<0 || bar.real_volume<0 || bar.spread<0)
      { error="malformed_or_unordered_rates"; return false; }
   }
   return true;
}
bool VxAggregateH4(const MqlRates &h1[],MqlRates &h4[],string &error)
{
   int size=ArraySize(h1),count=0;
   if(ArrayResize(h4,size/4)!=size/4) { error="allocation_failed"; return false; }
   for(int i=0;i<size;)
   {
      datetime start=(datetime)(((long)h1[i].time/14400)*14400);
      int end=i+1;
      while(end<size && (long)h1[end].time/14400==(long)start/14400) end++;
      bool exact=end-i==4;
      if(exact)
         for(int j=0;j<4;j++)
            if(h1[i+j].time!=(datetime)((long)start+j*3600)) exact=false;
      if(exact)
      {
         MqlRates bar=h1[i]; bar.time=start; bar.real_volume=0;
         for(int j=1;j<4;j++)
         {
            bar.high=MathMax(bar.high,h1[i+j].high); bar.low=MathMin(bar.low,h1[i+j].low);
            if(h1[i+j].tick_volume>LONG_MAX-bar.tick_volume)
            { ArrayResize(h4,0); error="volume_overflow"; return false; }
            bar.tick_volume+=h1[i+j].tick_volume;
         }
         bar.close=h1[i+3].close; bar.spread=h1[i+3].spread;
         h4[count++]=bar;
      }
      i=end;
   }
   ArrayResize(h4,count);
   if(count==0) { error="no_complete_h4"; return false; }
   return true;
}

bool VxIndicators(const MqlRates &rates[],VxFeature &out[],string &error)
{
   int size=ArraySize(rates);
   if(ArrayResize(out,size)!=size) { error="allocation_failed"; return false; }
   double e20=0,e50=0,e200=0,fast=0,slow=0,macdSignal=0;
   double atr=EMPTY_VALUE,gain=EMPTY_VALUE,loss=EMPTY_VALUE;
   double trSum=0,gainSum=0,lossSum=0,latestHigh=EMPTY_VALUE,latestLow=EMPTY_VALUE;
   for(int i=0;i<size;i++)
   {
      VxFeature f; VxResetFeature(f);
      double close=rates[i].close;
      if(i==0) { e20=close; e50=close; e200=close; fast=close; slow=close; }
      else
      {
         e20=VxEma(e20,close,20); e50=VxEma(e50,close,50); e200=VxEma(e200,close,200);
         fast=VxEma(fast,close,12); slow=VxEma(slow,close,26);
      }
      if(i>=19) f.ema20=e20;
      if(i>=49) f.ema50=e50;
      if(i>=199) f.ema200=e200;
      double tr=rates[i].high-rates[i].low;
      if(i>0) tr=MathMax(tr,MathMax(MathAbs(rates[i].high-rates[i-1].close),MathAbs(rates[i].low-rates[i-1].close)));
      if(i<14) trSum+=tr;
      if(i==13) atr=trSum/14.0;
      if(i>13) atr=VxWilderNext(atr,tr);
      if(!VxValid(trSum) || (i>=13 && !VxValid(atr)))
      { error="indicator_numeric_overflow"; return false; }
      f.atr=atr;
      if(i>0)
      {
         double change=close-rates[i-1].close,up=MathMax(change,0.0),down=MathMax(-change,0.0);
         if(i<=14) { gainSum+=up; lossSum+=down; }
         if(i==14) { gain=gainSum/14.0; loss=lossSum/14.0; }
         if(i>14) { gain=VxWilderNext(gain,up); loss=VxWilderNext(loss,down); }
         if(!VxValid(gainSum) || !VxValid(lossSum) || (i>=14 && (!VxValid(gain) || !VxValid(loss))))
         { error="indicator_numeric_overflow"; return false; }
         if(i>=14) f.rsi=(gain==0 && loss==0)?50.0:loss==0?100.0:gain==0?0.0:100.0-100.0/(1.0+gain/loss);
      }
      if(i>=3) f.rocPrice=close-rates[i-3].close;
      if(i>=25)
      {
         double macd=fast-slow;
         macdSignal=i==25?macd:VxEma(macdSignal,macd,9);
         if(i>=33) f.macdHist=macd-macdSignal;
      }
      if(i>=20)
      {
         double high=rates[i-20].high,low=rates[i-20].low,volume=0;
         for(int j=i-20;j<i;j++)
         { high=MathMax(high,rates[j].high); low=MathMin(low,rates[j].low); volume+=(double)rates[j].tick_volume; }
         f.priorHigh=high; f.priorLow=low; f.priorVolume=volume/20.0;
      }
      if(i>=4)
      {
         int centre=i-2; bool high=true,low=true;
         for(int j=i-4;j<=i;j++)
            if(j!=centre)
            { high=high && rates[centre].high>rates[j].high; low=low && rates[centre].low<rates[j].low; }
         if(high) { f.pivotHigh=rates[centre].high; latestHigh=f.pivotHigh; }
         if(low) { f.pivotLow=rates[centre].low; latestLow=f.pivotLow; }
      }
      f.swingHigh=latestHigh; f.swingLow=latestLow;
      if(VxValid(f.ema200))
      {
         if(close>e20 && e20>e50 && e50>e200) f.alignment=1;
         if(close<e20 && e20<e50 && e50<e200) f.alignment=-1;
         if(i>=5 && VxValid(out[i-5].ema20) && VxValid(atr) && atr>0)
         {
            double stack=(VxSign(close-e20)+VxSign(e20-e50)+VxSign(e50-e200))/3.0*100.0;
            double slope=VxClip(100.0*(e20-out[i-5].ema20)/atr);
            if(VxValid(slope)) f.trendScore=.75*stack+.25*slope;
         }
      }
      if(i>=63)
      {
         double prior[50]; bool valid=true;
         for(int j=0;j<50;j++) { prior[j]=out[i-50+j].atr; valid=valid && VxValid(prior[j]); }
         if(valid) { ArraySort(prior); f.atrBaseline=(prior[24]+prior[25])/2.0; }
      }
      out[i]=f;
   }
   return true;
}

void VxChooseMode(VxSignal &row,const bool sessionIdeal,const bool eligible)
{
   row.mode="FROZEN"; row.signal=0;
   if(!eligible || !VxValid(row.orion) || !VxValid(row.vortex) || !VxValid(row.nova) ||
      !VxValid(row.luna) || !VxValid(row.kira) || !VxValid(row.atlas) || !VxValid(row.consensus)) return;
   int direction=VxSign(row.consensus);
   if(direction==0) return;
   double o=row.orion*direction,v=row.vortex*direction,n=row.nova*direction;
   double l=row.luna*direction,a=row.atlas*direction,k=row.kira,strength=MathAbs(row.consensus);
   bool aligned=row.h1Alignment==direction && row.h4Alignment==direction;
   bool normal=strength>=72 && o>=70 && v>=55 && n>=75 && l>=55 && k>=45 && k<85 && a>=-35;
   bool aggressive=normal && strength>=78 && o>=75 && n>=80 && v>=65 && l>=70 && a>=50 && aligned;
   bool extreme=aggressive && strength>=82 && o>=80 && v>=70 && n>=80 && l>=80 && a>=70 && k>=60 && k<=84 && aligned && sessionIdeal;
   row.mode=extreme?"EXTREME":aggressive?"AGGRESSIVE":normal?"NORMAL":"FROZEN";
   row.signal=row.mode=="FROZEN"?0:direction;
}
int VxAsOf(const MqlRates &rates[],const int seconds,const datetime decision,int &cursor)
{
   while(cursor+1<ArraySize(rates) && (long)rates[cursor+1].time+seconds<=(long)decision) cursor++;
   return cursor;
}
bool VxFresh(const datetime closedAt,const datetime decision,const int seconds)
{ return(closedAt>0 && decision>=closedAt && (long)decision-(long)closedAt<seconds); }

bool VxBuildSignals(const MqlRates &m5[],const MqlRates &m15[],const MqlRates &h1[],
                    const VxExternal &external[],VxSignal &output[],string &error)
{
   error=""; ArrayResize(output,0);
   if(!VxValidateRates(m5,300,error) || !VxValidateRates(m15,900,error) || !VxValidateRates(h1,3600,error)) return false;
   for(int i=0;i<ArraySize(external);i++)
      if((long)external[i].decisionTime<0 || (long)external[i].decisionTime%300!=0 ||
         (i>0 && external[i].decisionTime<=external[i-1].decisionTime))
      { error="malformed_or_unordered_external_times"; return false; }
   MqlRates h4[];
   if(!VxAggregateH4(h1,h4,error)) return false;
   VxFeature f5[],f15[],f1[],f4[];
   if(!VxIndicators(m5,f5,error) || !VxIndicators(m15,f15,error) ||
      !VxIndicators(h1,f1,error) || !VxIndicators(h4,f4,error)) return false;
   int size=ArraySize(m5);
   if(ArrayResize(output,size)!=size) { error="allocation_failed"; return false; }
   int c15=-1,c1=-1,c4=-1,ce=0,highCount=0,lowCount=0;
   double lastHigh=EMPTY_VALUE,oldHigh=EMPTY_VALUE,lastLow=EMPTY_VALUE,oldLow=EMPTY_VALUE;
   int breakBar=-1,breakSide=0,sweepBar=-1,sweepSide=0; double breakLevel=EMPTY_VALUE;
   for(int i=0;i<size;i++)
   {
      VxSignal row; VxResetSignal(row);
      row.barOpen=m5[i].time; row.decisionTime=(datetime)((long)row.barOpen+300);
      int a15=VxAsOf(m15,900,row.decisionTime,c15),a1=VxAsOf(h1,3600,row.decisionTime,c1),a4=VxAsOf(h4,14400,row.decisionTime,c4);
      if(a15>=0) { row.m15ClosedAt=(datetime)((long)m15[a15].time+900); row.atr=f15[a15].atr; }
      if(a1>=0) { row.h1ClosedAt=(datetime)((long)h1[a1].time+3600); row.h1Alignment=f1[a1].alignment; }
      if(a4>=0) { row.h4ClosedAt=(datetime)((long)h4[a4].time+14400); row.h4Alignment=f4[a4].alignment; }
      row.m15Fresh=VxFresh(row.m15ClosedAt,row.decisionTime,900);
      row.h1Fresh=VxFresh(row.h1ClosedAt,row.decisionTime,3600);
      row.h4Fresh=VxFresh(row.h4ClosedAt,row.decisionTime,14400);
      bool contextFresh=row.m15Fresh && row.h1Fresh && row.h4Fresh;
      VxExternal ext; VxResetExternal(ext);
      while(ce<ArraySize(external) && external[ce].decisionTime<row.decisionTime) ce++;
      if(ce<ArraySize(external) && external[ce].decisionTime==row.decisionTime) ext=external[ce];
      if(contextFresh && VxValid(f15[a15].trendScore) && VxValid(f1[a1].trendScore) && VxValid(f4[a4].trendScore))
      { row.orion=.20*f15[a15].trendScore+.40*f1[a1].trendScore+.40*f4[a4].trendScore; row.orionReason="weighted_ema_stack_and_slope"; }
      VxFeature f=f5[i]; double atr=row.atr;
      if(VxValid(f.rsi) && VxValid(f.macdHist) && VxValid(f.rocPrice) && VxValid(f.atr) && f.atr>0)
      {
         double momentumRsi=VxClip(4.0*(f.rsi-50.0));
         double momentumMacd=VxClip(400.0*f.macdHist/f.atr);
         double momentumRoc=VxClip(50.0*f.rocPrice/f.atr);
         if(VxValid(momentumRsi) && VxValid(momentumMacd) && VxValid(momentumRoc))
         { row.vortex=.4*momentumRsi+.35*momentumMacd+.25*momentumRoc; row.vortexReason="rsi_macd_roc3"; }
      }
      // Capture the prior confirmed levels before publishing this bar's pivots.
      double priorHigh=lastHigh,priorLow=lastLow;
      if(VxValid(f.pivotHigh)) { oldHigh=lastHigh; lastHigh=f.pivotHigh; highCount++; }
      if(VxValid(f.pivotLow)) { oldLow=lastLow; lastLow=f.pivotLow; lowCount++; }
      if(highCount>=2 && lowCount>=2 && VxValid(atr) && atr>0)
      {
         int structure=lastHigh>oldHigh && lastLow>oldLow?1:lastHigh<oldHigh && lastLow<oldLow?-1:0;
         double previous=i>0?m5[i-1].close:EMPTY_VALUE;
         bool bull=VxValid(priorHigh) && VxValid(previous) && previous<=priorHigh+.05*atr && priorHigh+.05*atr<m5[i].close;
         bool bear=VxValid(priorLow) && VxValid(previous) && previous>=priorLow-.05*atr && priorLow-.05*atr>m5[i].close;
         int broken=bull && !bear?1:bear && !bull?-1:0;
         if(bull && bear) { breakBar=-1; row.nova=0; row.novaReason="conflicting_breaks"; }
         else
         {
            if(broken!=0) { breakBar=i; breakSide=broken; breakLevel=broken==1?priorHigh:priorLow; }
            bool touched=breakBar>=0 && MathAbs((breakSide==1?m5[i].low:m5[i].high)-breakLevel)<=.15*atr;
            bool retest=breakBar>=0 && i-breakBar>=1 && i-breakBar<=6 && touched && breakSide*(m5[i].close-breakLevel)>0 && structure==breakSide;
            if(broken!=0 && broken!=structure) { row.nova=50.0*broken; row.novaReason="break_without_aligned_structure"; }
            else if(structure!=0 && (broken==structure || retest)) { row.nova=100.0*structure; row.novaReason=broken!=0?"aligned_break":"aligned_retest"; }
            else { row.nova=70.0*structure; row.novaReason=structure!=0?"ordered_structure":"unresolved_structure"; }
         }
      }
      if(VxValid(atr) && atr>0 && VxValid(f.priorHigh) && VxValid(f.priorLow))
      {
         double highs[4],lows[4];
         highs[0]=f.priorHigh; highs[1]=ext.asiaHigh; highs[2]=ext.londonHigh; highs[3]=ext.newyorkHigh;
         lows[0]=f.priorLow; lows[1]=ext.asiaLow; lows[2]=ext.londonLow; lows[3]=ext.newyorkLow;
         double body=MathAbs(m5[i].close-m5[i].open);
         bool lower=MathMin(m5[i].open,m5[i].close)-m5[i].low>=body;
         bool upper=m5[i].high-MathMax(m5[i].open,m5[i].close)>=body;
         bool bull=false,bear=false;
         for(int j=0;j<4;j++)
         {
            bull=bull || (lower && VxValid(lows[j]) && m5[i].low<=lows[j]-.05*atr && m5[i].close>lows[j]);
            bear=bear || (upper && VxValid(highs[j]) && m5[i].high>=highs[j]+.05*atr && m5[i].close<highs[j]);
         }
         if(bull && bear) { sweepBar=-1; row.luna=0; row.lunaReason="conflicting_sweeps"; }
         else if(bull || bear) { sweepBar=i; sweepSide=bull?1:-1; row.luna=85.0*sweepSide; row.lunaReason="confirmed_sweep"; }
         else if(sweepBar>=0 && i-sweepBar<=3) { row.luna=sweepSide*(85.0-5.0*(i-sweepBar)); row.lunaReason="decaying_sweep"; }
         else { row.luna=0; row.lunaReason="no_sweep"; }
      }
      if(!row.m15Fresh) { row.nova=EMPTY_VALUE; row.luna=EMPTY_VALUE; row.novaReason="m15_context_stale"; row.lunaReason="m15_context_stale"; }
      if(row.m15Fresh && VxValid(atr) && atr>0 && VxValid(f15[a15].atrBaseline) && f15[a15].atrBaseline>0)
      {
         double ratio=atr/f15[a15].atrBaseline,relative=atr/m15[a15].close;
         if(VxValid(ratio) && VxValid(relative))
         {
            row.kira=ratio>=1.8 || relative>.01?90.0:relative<.00025 || ratio<.5?20.0:ratio<.8?50.0:75.0;
            row.kiraReason=row.kira>=85?"too_wild":row.kira<45?"too_quiet":"volatility_quality";
         }
      }
      // .001 is the frozen research point assumption, never guessed from a terminal.
      double spread=(double)m5[i].spread*.001;
      bool executionKnown=VxValid(spread) && spread>0 && VxValid(atr) && atr>0 && row.m15Fresh;
      row.executionValid=executionKnown && spread<=MathMin(.60,.10*atr);
      bool macroValid=ext.macroValid && VxValid(ext.dxyRoc) && VxValid(ext.us10yChange);
      double macroDollar=EMPTY_VALUE,macroYield=EMPTY_VALUE;
      if(macroValid)
      {
         macroDollar=VxClip(-100.0*ext.dxyRoc/.20); macroYield=VxClip(-100.0*ext.us10yChange/.05);
         macroValid=VxValid(macroDollar) && VxValid(macroYield);
      }
      bool atlasValid=ext.newsValid && macroValid && ext.sessionValid && executionKnown;
      if(atlasValid) row.atlas=.6*macroDollar+.4*macroYield;
      row.atlasReason=!ext.newsValid?"calendar_invalid":!macroValid?"macro_invalid":!ext.sessionValid?"session_invalid":!executionKnown?"execution_input_invalid":ext.newsBlocked?"news_blocked":!row.executionValid?"spread_blocked":"macro_context_valid";
      row.orion=VxClip(row.orion); row.vortex=VxClip(row.vortex); row.nova=VxClip(row.nova); row.luna=VxClip(row.luna); row.atlas=VxClip(row.atlas);
      bool finite=VxValid(row.orion) && VxValid(row.vortex) && VxValid(row.nova) && VxValid(row.luna) && VxValid(row.kira) && VxValid(row.atlas);
      if(finite) row.consensus=VxClip((.20*row.orion+.15*row.vortex+.20*row.nova+.20*row.luna+.15*row.atlas)/.90*(.90+.10*row.kira/100.0));
      row.ready=finite && VxValid(row.consensus) && contextFresh && row.executionValid && ext.newsValid && !ext.newsBlocked && atlasValid;
      VxChooseMode(row,ext.sessionIdeal,row.ready);
      row.swingLow=f.swingLow; row.swingHigh=f.swingHigh;
      if(VxValid(atr) && VxValid(f.swingLow))
      {
         double distance=MathMax(1.4*atr,m5[i].close-f.swingLow+.1*atr);
         if(VxValid(distance) && f.swingLow<m5[i].close && distance>=.35*atr && distance<=2.2*atr) row.stopLong=m5[i].close-distance;
      }
      if(VxValid(atr) && VxValid(f.swingHigh))
      {
         double distance=MathMax(1.4*atr,f.swingHigh-m5[i].close+.1*atr);
         if(VxValid(distance) && f.swingHigh>m5[i].close && distance>=.35*atr && distance<=2.2*atr) row.stopShort=m5[i].close+distance;
      }
      output[i]=row;
   }
   return true;
}
#endif
