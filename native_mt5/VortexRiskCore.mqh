// Pure risk planning only. No broker, account, orders, files, network, or clocks.
// VxrSize receives calculator facts for the EXACT supplied, rounded stop.
// lossPerLot includes adverse stop slippage, but excludes costReservePerLot.
// Caller must separately verify USD/DEMO identity, costs, history, ownership,
// fact freshness, broker calculators, and final proposed-volume risk/margin.
// sizing.freeMargin is raw broker free margin. Campaign planning separately
// deducts all account usedMargin from its equity-based margin allocation.
// Neither allowed=true nor any stress calculation authorizes execution.
// KILL is a planning brake, never an instruction to submit a liquidation order.
// Exit-policy output is allocation only: single_trailing retains full 2.5R TP,
// +1R cost-BE and +1.5R trailing; split runner has SL and TP=0 after TP2.
// Stop/target updates, cost-BE calculation, fill confirmation, and persistence
// remain the separate adapter's responsibility; this module cannot confirm them.
#ifndef VORTEX_RISK_CORE_MQH
#define VORTEX_RISK_CORE_MQH
#define VORTEX_NATIVE_RISK_VERSION "v0.2-risk-parity-1"

struct VxrParts { double tp1Lots,tp2Lots,runnerLots; bool split; };
struct VxrGate { string mode,reason; double riskFraction,drawdown; };
struct VxrSizingFacts
{
   bool metadataValid,lossEstimateValid,marginEstimateValid;
   int side,digits;
   double equity,riskFraction,maxRiskFraction,entry,stop;
   double lotMin,lotStep,lotMax,tickSize,minStopDistance;
   double freeMargin,maxMarginFraction,lossPerLot,costReservePerLot,marginPerLot;
};
struct VxrPlan
{
   bool allowed,stressOnly,executionAuthorized;
   string reason,mode,exitPolicy;
   double lots,riskCash,margin,budget,minimumRisk,stop,riskFraction;
   double tp1Lots,tp2Lots,runnerLots,campaignNominalAfter,campaignOpenRiskAfter;
   int addLevel;
};
struct VxrCampaignFacts
{
   VxrSizingFacts sizing;
   double dayStartEquity;
   int lossStreak;
   string requestedMode,profile;
   bool connected,dataFresh,protectiveOrdersConfirmed,persistentFrozen,dailyKilled,extremeDisabled;
   bool capitalValid,reconciled,ownershipValid,pendingIntent,signalReady;
   bool newsValid,newsBlocked,macroValid,sessionValid,quoteFresh,decisionFresh,researchStressPermitted;
   int campaignCount,adds,campaignSide;
   bool baseOpen,baseBreakevenConfirmed,allEarlierBreakevenConfirmed,allLegsStrictlyProfitable;
   double campaignStartingEquity,campaignNominalRisk,currentOpenRisk,closedGainR,consensus,orion,nova;
   double atrM15,liquidationPrice,spreadPrice;
   double usedMargin;
   bool currentRiskValid,marginAllocationValid;
};

bool VxrFinite(const double value)
{ return(value!=EMPTY_VALUE && MathIsValidNumber(value)); }
void VxrResetSizing(VxrSizingFacts &x)
{
   x.metadataValid=false; x.lossEstimateValid=false; x.marginEstimateValid=false;
   x.side=0; x.digits=-1;
   x.equity=0; x.riskFraction=0; x.maxRiskFraction=0; x.entry=0; x.stop=0;
   x.lotMin=0; x.lotStep=0; x.lotMax=0; x.tickSize=0; x.minStopDistance=0;
   x.freeMargin=0; x.maxMarginFraction=0; x.lossPerLot=0; x.costReservePerLot=0; x.marginPerLot=0;
}
void VxrResetPlan(VxrPlan &x)
{
   x.allowed=false; x.stressOnly=false; x.executionAuthorized=false;
   x.reason="invalid_risk_input"; x.mode="FROZEN"; x.exitPolicy="";
   x.lots=0; x.riskCash=0; x.margin=0; x.budget=0; x.minimumRisk=0; x.stop=0; x.riskFraction=0;
   x.tp1Lots=0; x.tp2Lots=0; x.runnerLots=0; x.campaignNominalAfter=0; x.campaignOpenRiskAfter=0; x.addLevel=0;
}
void VxrResetCampaign(VxrCampaignFacts &x)
{
   VxrResetSizing(x.sizing);
   x.dayStartEquity=0; x.lossStreak=0; x.requestedMode="FROZEN"; x.profile="";
   x.connected=false; x.dataFresh=false; x.protectiveOrdersConfirmed=false;
   x.persistentFrozen=false; x.dailyKilled=false; x.extremeDisabled=false;
   x.capitalValid=false; x.reconciled=false; x.ownershipValid=false; x.pendingIntent=false; x.signalReady=false;
   x.newsValid=false; x.newsBlocked=true; x.macroValid=false; x.sessionValid=false;
   x.quoteFresh=false; x.decisionFresh=false; x.researchStressPermitted=false;
   x.campaignCount=0; x.adds=0; x.campaignSide=0;
   x.baseOpen=false; x.baseBreakevenConfirmed=false; x.allEarlierBreakevenConfirmed=false; x.allLegsStrictlyProfitable=false;
   x.campaignStartingEquity=0; x.campaignNominalRisk=0; x.currentOpenRisk=0;
   x.closedGainR=0; x.consensus=0; x.orion=0; x.nova=0; x.currentRiskValid=false;
   x.atrM15=0; x.liquidationPrice=0; x.spreadPrice=0;
   x.usedMargin=EMPTY_VALUE; x.marginAllocationValid=false;
}
bool VxrReject(VxrPlan &plan,const string reason)
{ VxrResetPlan(plan); plan.reason=reason; return false; }

double VxrFloorLots(const double value,const double step)
{
   // Native double arithmetic can conservatively underfloor at a decimal edge.
   // No epsilon is added to the available volume and the result never exceeds it.
   // Metadata supports volume precision through 8 decimals, not arbitrary Decimal.
   if(!VxrFinite(value) || value<=0 || !VxrFinite(step) || step<.00000001 ||
      MathAbs(NormalizeDouble(step,8)-step)>step*1e-9) return 0;
   double units=MathFloor(value/step);
   if(!VxrFinite(units) || units<1 || units>9007199254740991.0) return 0;
   double result=NormalizeDouble(units*step,8);
   if(result>value) { units--; result=NormalizeDouble(units*step,8); }
   return(VxrFinite(result) && result>0 && result<=value?result:0);
}
double VxrRoundPrice(const double value,const double tick,const bool up=false)
{
   if(!VxrFinite(value) || value<=0 || !VxrFinite(tick) || tick<.00000001 ||
      MathAbs(NormalizeDouble(tick,8)-tick)>tick*1e-9) return EMPTY_VALUE;
   double ratio=value/tick;
   if(!VxrFinite(ratio) || ratio>9007199254740991.0) return EMPTY_VALUE;
   // Canonical decimal tick first, then choose the outward side by comparison.
   // This avoids a spurious extra tick when 1998.6/.001 is integer-minus-epsilon.
   double units=MathRound(ratio);
   double result=StringToDouble(DoubleToString(units*tick,8));
   if(up && result<value) result=StringToDouble(DoubleToString((units+1)*tick,8));
   if(!up && result>value) result=StringToDouble(DoubleToString((units-1)*tick,8));
   bool outward=up?result>=value:result<=value;
   return(VxrFinite(result) && result>0 && outward?result:EMPTY_VALUE);
}
bool VxrExactParts(const double lots,const double lotMin,const double lotStep,VxrParts &parts)
{
   parts.tp1Lots=0; parts.tp2Lots=0; parts.runnerLots=0; parts.split=false;
   if(!VxrFinite(lots) || lots<=0 || !VxrFinite(lotMin) || lotMin<=0 || !VxrFinite(lotStep) || lotStep<=0) return false;
   double quarter=lots/4.0,half=lots/2.0;
   if(quarter<lotMin-1e-10 || half<lotMin-1e-10 ||
      MathAbs(VxrFloorLots(quarter+1e-12,lotStep)-quarter)>1e-9 ||
      MathAbs(VxrFloorLots(half+1e-12,lotStep)-half)>1e-9) return false;
   parts.tp1Lots=NormalizeDouble(quarter,8); parts.tp2Lots=parts.tp1Lots;
   parts.runnerLots=NormalizeDouble(half,8); parts.split=true;
   return true;
}
void VxrModeGate(const double dayStartEquity,const double equity,const int lossStreak,
                 const string requestedMode,const bool connected,const bool dataFresh,
                 const bool protectionConfirmed,VxrGate &out)
{
   // Exact frozen helper ordering and floating DD formula. Composite below adds
   // conservative cash-boundary checks and persistent-state checks explicitly.
   out.mode="FROZEN"; out.reason="invalid_equity"; out.riskFraction=0; out.drawdown=0;
   if(!VxrFinite(dayStartEquity) || !VxrFinite(equity) || dayStartEquity<=0) return;
   out.drawdown=MathMax(0.0,1.0-equity/dayStartEquity);
   if(out.drawdown>=.15) { out.mode="KILL"; out.reason="daily_drawdown_15"; return; }
   if(lossStreak>=3) { out.reason="three_losses"; return; }
   if(!connected || !dataFresh || !protectionConfirmed) { out.reason="connection_data_or_protection"; return; }
   double fraction=requestedMode=="NORMAL"?.02:requestedMode=="AGGRESSIVE"?.035:requestedMode=="EXTREME"?.05:0;
   if(fraction==0) { out.reason="invalid_mode"; return; }
   if(requestedMode=="EXTREME" && (out.drawdown>=.10 || lossStreak>=2)) { out.reason="extreme_disabled"; return; }
   out.mode=requestedMode; out.reason="PASS"; out.riskFraction=fraction*(lossStreak>=2?.5:1.0);
}
bool VxrPrepareStop(const double entry,const double structuralStop,const double atr,
                    const int side,const double tickSize,double &stop,string &reason)
{
   // entry must already include adverse entry slippage. StructuralStop is the
   // frozen signal candidate, already .1 ATR beyond structural invalidation.
   stop=0; reason="invalid_stop";
   if(!VxrFinite(entry) || entry<=0 || !VxrFinite(structuralStop) || structuralStop<=0 ||
      !VxrFinite(atr) || atr<=0 || (side!=1 && side!=-1)) return false;
   double raw=side==1?MathMin(structuralStop,entry-1.4*atr):MathMax(structuralStop,entry+1.4*atr);
   double rounded=VxrRoundPrice(raw,tickSize,side==-1),distance=side*(entry-rounded);
   if(!VxrFinite(rounded) || !VxrFinite(distance)) return false;
   if(distance<.35*atr || distance>2.2*atr+1e-8) { reason="stop_exceeds_atr_cap"; return false; }
   stop=rounded; reason="PASS"; return true;
}
bool VxrSize(const VxrSizingFacts &x,VxrPlan &plan)
{
   VxrResetPlan(plan);
   if(!x.metadataValid) return VxrReject(plan,"metadata_unverified");
   if(!x.lossEstimateValid) return VxrReject(plan,"loss_estimate_unverified");
   if(!x.marginEstimateValid) return VxrReject(plan,"margin_estimate_unverified");
   if(!VxrFinite(x.equity) || !VxrFinite(x.riskFraction) || !VxrFinite(x.maxRiskFraction) ||
      !VxrFinite(x.entry) || !VxrFinite(x.stop) || !VxrFinite(x.lotMin) || !VxrFinite(x.lotStep) ||
      !VxrFinite(x.lotMax) || !VxrFinite(x.tickSize) || !VxrFinite(x.minStopDistance) ||
      !VxrFinite(x.maxMarginFraction) || !VxrFinite(x.lossPerLot) || !VxrFinite(x.costReservePerLot) ||
      !VxrFinite(x.marginPerLot)) return false;
   if(x.equity<=0 || x.entry<=0 || x.stop<=0 || (x.side!=1 && x.side!=-1) ||
      !(x.riskFraction>0 && x.riskFraction<=x.maxRiskFraction && x.maxRiskFraction<=.10) ||
      x.lotMin<=0 || x.lotStep<.00000001 || x.lotMax<x.lotMin || x.tickSize<.00000001 ||
      x.minStopDistance<0 || !(x.maxMarginFraction>0 && x.maxMarginFraction<=1) ||
      x.lossPerLot<=0 || x.costReservePerLot<0 || x.marginPerLot<0 || x.digits<0 || x.digits>8 ||
      MathAbs(NormalizeDouble(x.tickSize,x.digits)-x.tickSize)>x.tickSize*1e-9 ||
      MathAbs(NormalizeDouble(x.lotStep,8)-x.lotStep)>x.lotStep*1e-9) return false;
   double ratio=x.stop/x.tickSize;
   if(!VxrFinite(ratio) || ratio>9007199254740991.0 || MathAbs(ratio-MathRound(ratio))>1e-7)
      return VxrReject(plan,"unaligned_stop");
   double distance=x.side*(x.entry-x.stop);
   if(!VxrFinite(distance) || distance<=MathMax(0.0,x.minStopDistance) || distance<x.tickSize)
      return VxrReject(plan,"invalid_stop");
   double perLot=x.lossPerLot+x.costReservePerLot,budget=x.equity*x.riskFraction;
   if(!VxrFinite(perLot) || perLot<=0 || !VxrFinite(budget) || !VxrFinite(x.lotMin*perLot)) return false;
   double lots=VxrFloorLots(MathMin(budget/perLot,x.lotMax),x.lotStep);
   if(lots<x.lotMin-1e-10)
   { plan.reason="min_lot"; plan.minimumRisk=x.lotMin*perLot; plan.budget=budget; return false; }
   double risk=lots*perLot,margin=lots*x.marginPerLot;
   // A floating boundary can only reduce size, never exceed the cash budget.
   if(VxrFinite(risk) && risk>budget)
   { lots=NormalizeDouble(lots-x.lotStep,8); risk=lots*perLot; margin=lots*x.marginPerLot; }
   if(lots<x.lotMin-1e-10 || !VxrFinite(risk) || !VxrFinite(margin) || risk>budget)
      return VxrReject(plan,"risk_recheck");
   if(!VxrFinite(x.freeMargin) || x.freeMargin<0) return VxrReject(plan,"invalid_margin");
   if(margin>MathMin(x.freeMargin,x.equity*x.maxMarginFraction)+1e-10) return VxrReject(plan,"margin");
   VxrParts parts;
   bool split=VxrExactParts(lots,x.lotMin,x.lotStep,parts);
   plan.allowed=true; plan.reason="PASS"; plan.lots=lots; plan.riskCash=risk; plan.margin=margin;
   plan.budget=budget; plan.stop=x.stop; plan.riskFraction=x.riskFraction; plan.stressOnly=x.riskFraction>.05;
   plan.exitPolicy=split?"partial_25_25_50":"single_trailing";
   plan.tp1Lots=split?parts.tp1Lots:0; plan.tp2Lots=split?parts.tp2Lots:0; plan.runnerLots=split?parts.runnerLots:lots;
   return true;
}
bool VxrPlanCampaign(const VxrCampaignFacts &x,VxrPlan &plan)
{
   VxrResetPlan(plan);
   if(!VxrFinite(x.dayStartEquity) || x.dayStartEquity<=0 || !VxrFinite(x.sizing.equity) || x.lossStreak<0)
      return VxrReject(plan,"invalid_equity");
   if(x.dailyKilled || x.sizing.equity<=x.dayStartEquity*.85)
   { VxrReject(plan,"daily_drawdown_15"); plan.mode="KILL"; return false; }
   if(x.persistentFrozen || x.lossStreak>=3) return VxrReject(plan,"three_losses");
   if(!x.capitalValid) return VxrReject(plan,"capital_unverified");
   if(!x.reconciled || !x.ownershipValid || x.pendingIntent) return VxrReject(plan,"reconciliation_or_ownership");
   if(!x.signalReady || !x.newsValid || x.newsBlocked || !x.macroValid || !x.sessionValid || !x.quoteFresh || !x.decisionFresh)
      return VxrReject(plan,"mandatory_inputs_invalid");
   if(!x.currentRiskValid || !VxrFinite(x.currentOpenRisk) || x.currentOpenRisk<0 ||
      !VxrFinite(x.campaignNominalRisk) || x.campaignNominalRisk<0)
      return VxrReject(plan,"current_risk_unverified");
   VxrGate gate;
   VxrModeGate(x.dayStartEquity,x.sizing.equity,x.lossStreak,x.requestedMode,x.connected,x.dataFresh,x.protectiveOrdersConfirmed,gate);
   if(gate.mode=="FROZEN" || gate.mode=="KILL")
   { VxrReject(plan,gate.reason); plan.mode=gate.mode; return false; }
   if(x.requestedMode=="EXTREME" && (x.extremeDisabled || x.sizing.equity<=x.dayStartEquity*.90))
      return VxrReject(plan,"extreme_disabled");
   if(!VxrFinite(x.atrM15) || x.atrM15<=0 || !VxrFinite(x.spreadPrice) || x.spreadPrice<=0 ||
      x.spreadPrice>MathMin(.60,.10*x.atrM15)) return VxrReject(plan,"actual_spread_gate");
   double initialDistance=x.sizing.side*(x.sizing.entry-x.sizing.stop);
   if(!VxrFinite(initialDistance) || initialDistance<1.4*x.atrM15-1e-8 || initialDistance>2.2*x.atrM15+1e-8)
      return VxrReject(plan,"stop_exceeds_atr_cap");
   if(!VxrFinite(x.liquidationPrice) || x.liquidationPrice<=0 ||
      x.sizing.side*(x.liquidationPrice-x.sizing.stop)<=MathMax(0.0,x.sizing.minStopDistance) ||
      x.sizing.side*(x.sizing.entry-x.liquidationPrice)<=0)
      return VxrReject(plan,"stop_inside_spread_or_limit");
   bool stress=x.profile=="STRESS_075" || x.profile=="STRESS_10";
   if(x.profile!="CAP_NORMAL" && x.profile!="CAP_AGGRESSIVE" && x.profile!="BASELINE" && !stress)
      return VxrReject(plan,"invalid_profile");
   if(stress && !x.researchStressPermitted) return VxrReject(plan,"offline_stress_only");
   if(x.campaignCount<0 || x.campaignCount>1 || x.adds<0 || x.adds>2 ||
      (x.sizing.side!=1 && x.sizing.side!=-1)) return VxrReject(plan,"campaign_state_invalid");
   double riskFactor=x.lossStreak>=2?.5:1.0;
   double rawFraction=x.requestedMode=="NORMAL"?.02:x.requestedMode=="AGGRESSIVE"?.035:
      x.profile=="STRESS_075"?.075:x.profile=="STRESS_10"?.10:.05;
   if(x.profile=="CAP_NORMAL") rawFraction=MathMin(rawFraction,.02);
   if(x.profile=="CAP_AGGRESSIVE") rawFraction=MathMin(rawFraction,.035);
   int level=0;
   if(x.campaignCount==1)
   {
      if(!VxrFinite(x.campaignStartingEquity) || x.campaignStartingEquity<=0 || x.campaignNominalRisk<=0 || x.campaignSide!=x.sizing.side || x.adds>=2)
         return VxrReject(plan,"add_limit_or_direction");
      if(!x.baseOpen) return VxrReject(plan,"base_closed_no_add");
      if(!VxrFinite(x.closedGainR) || !VxrFinite(x.consensus) || !VxrFinite(x.orion) || !VxrFinite(x.nova) ||
         MathAbs(x.consensus)>100 || MathAbs(x.orion)>100 || MathAbs(x.nova)>100)
         return VxrReject(plan,"winner_inputs_invalid");
      level=x.adds+1;
      if(x.closedGainR<level || x.sizing.side*x.consensus<(level==1?78:82))
         return VxrReject(plan,"winner_threshold_not_met");
      if(!x.allLegsStrictlyProfitable) return VxrReject(plan,"loser_add_forbidden");
      if(!x.baseBreakevenConfirmed || (level==2 && !x.allEarlierBreakevenConfirmed))
         return VxrReject(plan,"breakeven_not_confirmed");
      if(level==2 && (x.sizing.side*x.orion<80 || x.sizing.side*x.nova<80))
         return VxrReject(plan,"second_add_votes");
      rawFraction=level==1?.015:.01;
   }
   else if(x.adds!=0 || x.baseOpen || x.campaignNominalRisk!=0 || x.currentOpenRisk!=0)
      return VxrReject(plan,"campaign_state_invalid");
   double cap=x.profile=="STRESS_10"?.10:.075;
   VxrSizingFacts sizing=x.sizing;
   sizing.riskFraction=rawFraction*riskFactor; sizing.maxRiskFraction=cap;
   // Live adapter has a fixed 25% margin allocation ceiling. Do not relax it.
   if(!VxrFinite(sizing.maxMarginFraction) || sizing.maxMarginFraction<=0 || sizing.maxMarginFraction>1)
      return VxrReject(plan,"invalid_risk_input");
   sizing.maxMarginFraction=MathMin(sizing.maxMarginFraction,.25);
   if(!x.marginAllocationValid || !VxrFinite(x.usedMargin) || x.usedMargin<0)
      return VxrReject(plan,"margin_allocation_unverified");
   if(!VxrFinite(sizing.freeMargin) || sizing.freeMargin<0) return VxrReject(plan,"invalid_margin");
   double remainingAllocation=MathMax(0.0,sizing.equity*sizing.maxMarginFraction-x.usedMargin);
   if(remainingAllocation<=0) return VxrReject(plan,"margin");
   sizing.freeMargin=MathMin(sizing.freeMargin,remainingAllocation);
   if(!VxrSize(sizing,plan)) return false;
   double start=x.campaignCount==1?x.campaignStartingEquity:x.sizing.equity;
   double nominal=x.campaignNominalRisk+plan.budget,open=x.currentOpenRisk+plan.riskCash;
   if(!VxrFinite(nominal) || nominal>start*cap+1e-9) return VxrReject(plan,"campaign_nominal_cap");
   if(!VxrFinite(open) || open>x.sizing.equity*cap+1e-9) return VxrReject(plan,"campaign_open_risk_cap");
   plan.mode=gate.mode; plan.stressOnly=stress; plan.addLevel=level;
   plan.campaignNominalAfter=nominal; plan.campaignOpenRiskAfter=open;
   return true;
}
#endif
