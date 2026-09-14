"""Synthetic native risk cases; frozen oracles and new safeguards are distinct."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import sys

REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO/"research_v02"))
from vortex_v02.risk import BrokerSpec,Costs,size_order,mode_gate,tick_price

KIND="SYNTHETIC_OFFLINE_RISK_V1"
CORE_VERSION="v0.2-risk-parity-1"
HARNESS_VERSION="VORTEX-NATIVE-RISK-PARITY-0.1"
SIZING_FIELDS=[("metadata_valid","metadataValid","bool"),("loss_estimate_valid","lossEstimateValid","bool"),
 ("margin_estimate_valid","marginEstimateValid","bool"),("side","side","int"),("digits","digits","int"),
 ("equity","equity","double"),("risk_fraction","riskFraction","double"),("max_risk_fraction","maxRiskFraction","double"),
 ("entry","entry","double"),("stop","stop","double"),("lot_min","lotMin","double"),("lot_step","lotStep","double"),
 ("lot_max","lotMax","double"),("tick_size","tickSize","double"),("min_stop_distance","minStopDistance","double"),
 ("free_margin","freeMargin","double"),("max_margin_fraction","maxMarginFraction","double"),
 ("loss_per_lot","lossPerLot","double"),("cost_reserve_per_lot","costReservePerLot","double"),
 ("margin_per_lot","marginPerLot","double")]
GATE_FIELDS=[("day_start_equity","dayStartEquity","double"),("equity","equity","double"),("loss_streak","lossStreak","int"),
 ("requested_mode","requestedMode","string"),("connected","connected","bool"),("data_fresh","dataFresh","bool"),
 ("protection_confirmed","protectiveOrdersConfirmed","bool")]
CAMPAIGN_FIELDS=[("day_start_equity","dayStartEquity","double"),("loss_streak","lossStreak","int"),
 ("requested_mode","requestedMode","string"),("profile","profile","string"),
 ("connected","connected","bool"),("data_fresh","dataFresh","bool"),("protection_confirmed","protectiveOrdersConfirmed","bool"),
 ("persistent_frozen","persistentFrozen","bool"),("daily_killed","dailyKilled","bool"),("extreme_disabled","extremeDisabled","bool"),
 ("capital_valid","capitalValid","bool"),("reconciled","reconciled","bool"),("ownership_valid","ownershipValid","bool"),
 ("pending_intent","pendingIntent","bool"),("signal_ready","signalReady","bool"),("news_valid","newsValid","bool"),
 ("news_blocked","newsBlocked","bool"),("macro_valid","macroValid","bool"),("session_valid","sessionValid","bool"),
 ("quote_fresh","quoteFresh","bool"),("decision_fresh","decisionFresh","bool"),
 ("research_stress_permitted","researchStressPermitted","bool"),("campaign_count","campaignCount","int"),
 ("adds","adds","int"),("campaign_side","campaignSide","int"),("base_open","baseOpen","bool"),
 ("base_breakeven_confirmed","baseBreakevenConfirmed","bool"),("earlier_breakeven_confirmed","allEarlierBreakevenConfirmed","bool"),
 ("all_legs_profitable","allLegsStrictlyProfitable","bool"),("campaign_starting_equity","campaignStartingEquity","double"),
 ("campaign_nominal_risk","campaignNominalRisk","double"),("current_open_risk","currentOpenRisk","double"),
 ("closed_gain_r","closedGainR","double"),("consensus","consensus","double"),("orion","orion","double"),
 ("nova","nova","double"),("current_risk_valid","currentRiskValid","bool"),
 ("atr_m15","atrM15","double"),("liquidation_price","liquidationPrice","double"),("spread_price","spreadPrice","double"),
 ("used_margin","usedMargin","double"),("margin_allocation_valid","marginAllocationValid","bool")]
STOP_FIELDS=[("entry","entry","double"),("structural_stop","structuralStop","double"),("atr","atr","double"),
             ("side","side","int"),("tick_size","tickSize","double")]
PLAN_FIELDS=[("allowed","allowed","bool"),("reason","reason","string"),("mode","mode","string"),
 ("exit_policy","exitPolicy","string"),("lots","lots","double"),("risk_cash","riskCash","double"),
 ("margin","margin","double"),("budget","budget","double"),("minimum_risk","minimumRisk","double"),
 ("stop","stop","double"),("risk_fraction","riskFraction","double"),("tp1_lots","tp1Lots","double"),
 ("tp2_lots","tp2Lots","double"),("runner_lots","runnerLots","double"),
 ("campaign_nominal_after","campaignNominalAfter","double"),("campaign_open_risk_after","campaignOpenRiskAfter","double"),
 ("add_level","addLevel","int"),("stress_only","stressOnly","bool"),("execution_authorized","executionAuthorized","bool")]
GATE_OUTPUT=[("mode","mode","string"),("reason","reason","string"),("risk_fraction","riskFraction","double"),("drawdown","drawdown","double")]
STOP_OUTPUT=[("allowed","allowed","bool"),("reason","reason","string"),("stop","stop","double")]
TABLES={"size":(SIZING_FIELDS,PLAN_FIELDS),"gate":(GATE_FIELDS,GATE_OUTPUT),
        "campaign":(SIZING_FIELDS+CAMPAIGN_FIELDS,PLAN_FIELDS),"stop":(STOP_FIELDS,STOP_OUTPUT)}
REFERENCES=["research_v02/vortex_v02/risk.py","research_v02/SPEC.md","live/execution_v02.py"]


def write(path,fields,rows):
    with Path(path).open("w",encoding="utf-8",newline="") as stream:
        writer=csv.writer(stream,lineterminator="\n");writer.writerow(["case_id"]+[f[0] for f in fields])
        for row in rows:
            values=[row["case_id"]]
            for name,_,kind in fields:
                x=row.get(name)
                if x is None or (isinstance(x,float) and not math.isfinite(x)):values.append("")
                elif kind in ("bool","int"):values.append(str(int(x)))
                elif kind=="double":values.append(format(float(x),".17g"))
                else:values.append(str(x))
            writer.writerow(values)


def empty_plan(reason="invalid_risk_input",**overrides):
    result={name:(False if kind=="bool" else "" if kind=="string" else 0) for name,_,kind in PLAN_FIELDS}
    result.update(reason=reason,mode="FROZEN");result.update(overrides)
    return result


def sized_case(name,**overrides):
    facts=dict(equity=50.,risk_fraction=.02,max_risk_fraction=.075,entry=2000.,stop=1999.5,side=1,
               contract_size=100.,lot_min=.01,lot_step=.01,lot_max=200.,tick_size=.001,leverage=2000.,
               min_stop_distance=0.,max_margin_fraction=.25,slippage=.03,commission=0.,free_margin=50.)
    facts.update(overrides)
    spec=BrokerSpec(**{k:facts[k] for k in BrokerSpec.__dataclass_fields__})
    costs=Costs(facts["slippage"],facts["commission"])
    expected=size_order(facts["equity"],facts["risk_fraction"],facts["entry"],facts["stop"],facts["side"],
                        spec,costs,facts["free_margin"],facts["max_risk_fraction"])
    rounded=tick_price(facts["stop"],facts["tick_size"],up=facts["side"]==-1)
    row={k:facts[k] for k,_,_ in SIZING_FIELDS if k in facts}
    row.update(case_id=name,metadata_valid=True,loss_estimate_valid=True,margin_estimate_valid=True,digits=3,stop=rounded,
               loss_per_lot=(facts["side"]*(facts["entry"]-rounded)+facts["slippage"])*facts["contract_size"],
               cost_reserve_per_lot=2*facts["commission"],margin_per_lot=facts["contract_size"]*facts["entry"]/facts["leverage"])
    result=empty_plan(expected["reason"])
    result.update({k:expected[k] for k in ("allowed","lots","risk_cash","margin","budget","minimum_risk","stop","exit_policy") if k in expected})
    if expected["allowed"]:
        result.update(tp1_lots=expected["parts"][0],tp2_lots=expected["parts"][1],runner_lots=expected["parts"][2],
                      risk_fraction=facts["risk_fraction"],stress_only=facts["risk_fraction"]>.05)
    return row,result,"frozen_size_order"


def size_cases():
    cases=[]
    for fraction,label in ((.02,"02"),(.035,"035"),(.05,"05"),(.075,"075"),(.10,"10")):
        cases.append(sized_case("profile_"+label,risk_fraction=fraction,max_risk_fraction=max(.075,fraction)))
    for name,overrides in [
        ("synthetic_reduced_equity",dict(equity=44.25,free_margin=44.25)),
        ("synthetic_equity_100",dict(equity=100.,free_margin=100.)),
        ("min_lot_no_roundup",dict(stop=1998.)),
        ("partial_004",dict(stop=1999.8)),
        ("fallback_003",dict(stop=1999.7)),
        ("fallback_002",dict(stop=1999.6)),
        ("floor_just_below_one_step",dict(equity=49.999999999,stop=1999.,slippage=0.)),
        ("floor_exact_one_step",dict(stop=1999.,slippage=0.)),
        ("floor_above_one_step",dict(equity=50.000000001,stop=1999.,slippage=0.)),
        ("round_long_outward",dict(stop=1999.5004)),
        ("round_short_outward",dict(stop=2000.4996,side=-1)),
        ("nondecimal_step_002",dict(lot_min=.02,lot_step=.02,stop=1999.8)),
        ("lot_max_cap",dict(lot_max=.02,stop=1999.8)),
        ("margin_fraction_blocks",dict(leverage=10.)),
        ("free_margin_blocks",dict(free_margin=.5)),
        ("free_margin_missing",dict(free_margin=float("nan"))),
        ("free_margin_negative",dict(free_margin=-1.)),
        ("commission_reserve",dict(commission=15.)),
        ("stress_slippage",dict(slippage=.10)),
        ("broker_stop_boundary",dict(stop=1999.5,min_stop_distance=.5)),
        ("risk_above_cap",dict(risk_fraction=.10)),
    ]:cases.append(sized_case(name,**overrides))
    base,_,_=sized_case("base")
    for name,changes,reason in [
        ("metadata_missing",{"metadata_valid":False},"metadata_unverified"),
        ("loss_quote_missing",{"loss_estimate_valid":False},"loss_estimate_unverified"),
        ("margin_quote_missing",{"margin_estimate_valid":False},"margin_estimate_unverified"),
        ("unaligned_supplied_stop",{"stop":1999.5004},"unaligned_stop"),
        ("invalid_equity",{"equity":float("nan")},"invalid_risk_input"),
        ("invalid_side",{"side":0},"invalid_risk_input"),
        ("zero_lot_step",{"lot_step":0.},"invalid_risk_input"),
        ("negative_cost_reserve",{"cost_reserve_per_lot":-1.},"invalid_risk_input"),
    ]:cases.append(({**base,**changes,"case_id":name},empty_plan(reason),"explicit_fail_closed_validator"))
    # These two cases explicitly document a conservative native-double policy:
    # no epsilon is added to the affordable raw volume. Frozen Decimal flooring
    # would permit .3/.6 respectively; native division underfloors one step.
    for name,equity,step,lots in [("native_decimal_03_by_01",50.,.1,.2),("native_decimal_06_by_02",100.,.2,.4)]:
        row={**base,"case_id":name,"equity":equity,"risk_fraction":.06,"entry":100.,"stop":99.,
             "lot_min":step,"lot_step":step,"tick_size":.1,"loss_per_lot":10.,"margin_per_lot":1.}
        expected=empty_plan("PASS",allowed=True,lots=lots,risk_cash=lots*10.,margin=lots,budget=equity*.06,
          stop=99.,risk_fraction=.06,stress_only=True,exit_policy="single_trailing",runner_lots=lots)
        cases.append((row,expected,"documented_native_conservative_decimal_floor"))
    return cases


def gate_cases():
    cases=[]
    def add(name,**changes):
        row=dict(case_id=name,day_start_equity=100.,equity=100.,loss_streak=0,requested_mode="NORMAL",
                 connected=True,data_fresh=True,protection_confirmed=True);row.update(changes)
        mode,reason,fraction=mode_gate(row["day_start_equity"],row["equity"],row["loss_streak"],row["requested_mode"],
                                      row["connected"],row["data_fresh"],row["protection_confirmed"])
        dd=max(0.,1-row["equity"]/row["day_start_equity"]) if row["day_start_equity"]>0 else 0.
        cases.append((row,dict(mode=mode,reason=reason,risk_fraction=fraction,drawdown=dd),"frozen_mode_gate"))
    for mode in ("NORMAL","AGGRESSIVE","EXTREME"):
        for streak in (0,1,2,3):add(mode.lower()+"_losses_"+str(streak),requested_mode=mode,loss_streak=streak)
    for equity in (90.000001,90.,89.999999,85.000001,85.,84.999999):
        add("dd_boundary_"+str(equity).replace(".","_"),requested_mode="EXTREME",equity=equity)
    for field in ("connected","data_fresh","protection_confirmed"):add(field+"_false",**{field:False})
    add("invalid_mode",requested_mode="UNKNOWN")
    add("invalid_day_start",day_start_equity=0.)
    add("kill_precedes_disconnect",equity=84.,connected=False)
    return cases


def campaign_cases():
    # Case expectations are prescribed independently: successful lot calculation
    # uses frozen size_order; rejection reasons specify one isolated safety rule.
    cases=[]
    def facts(name,equity=50.,side=1):
        row,_,_=sized_case(name,equity=equity,free_margin=equity,
                           side=side,stop=1999.5 if side==1 else 2000.5)
        row.update(day_start_equity=equity,loss_streak=0,requested_mode="NORMAL",profile="BASELINE",
          connected=True,data_fresh=True,protection_confirmed=True,persistent_frozen=False,daily_killed=False,
          extreme_disabled=False,capital_valid=True,reconciled=True,ownership_valid=True,pending_intent=False,
          signal_ready=True,news_valid=True,news_blocked=False,macro_valid=True,session_valid=True,
          quote_fresh=True,decision_fresh=True,research_stress_permitted=False,campaign_count=0,adds=0,
          campaign_side=side,base_open=False,base_breakeven_confirmed=False,earlier_breakeven_confirmed=False,
          all_legs_profitable=False,campaign_starting_equity=equity,campaign_nominal_risk=0.,current_open_risk=0.,
          closed_gain_r=0.,consensus=85.*side,orion=85.*side,nova=85.*side,current_risk_valid=True,
          atr_m15=.3,liquidation_price=2000.-side*.02,spread_price=.02,used_margin=0.,margin_allocation_valid=True)
        return row
    def allow(row,fraction,level=0):
        _,expected,_=sized_case(row["case_id"],equity=row["equity"],free_margin=row["free_margin"],
          risk_fraction=fraction,max_risk_fraction=.10 if row["profile"]=="STRESS_10" else .075,
          entry=row["entry"],stop=row["stop"],side=row["side"])
        if expected["allowed"]:
            expected.update(mode=row["requested_mode"],stress_only=row["profile"].startswith("STRESS_"),
              add_level=level,campaign_nominal_after=row["campaign_nominal_risk"]+expected["budget"],
              campaign_open_risk_after=row["current_open_risk"]+expected["risk_cash"])
        cases.append((row,expected,"frozen_size_order_with_prescribed_campaign_policy"))
    def reject(row,reason,mode="FROZEN"):
        cases.append((row,empty_plan(reason,mode=mode),"explicit_fail_closed_campaign_validator"))
    for name,mode,profile,fraction in [
      ("base_normal","NORMAL","BASELINE",.02),("base_aggressive","AGGRESSIVE","BASELINE",.035),
      ("base_extreme","EXTREME","BASELINE",.05),("cap_normal","EXTREME","CAP_NORMAL",.02),
      ("cap_aggressive","EXTREME","CAP_AGGRESSIVE",.035),("stress_075","EXTREME","STRESS_075",.075),
      ("stress_10","EXTREME","STRESS_10",.10),("stress_profile_normal","NORMAL","STRESS_10",.02)]:
        row=facts(name);row.update(requested_mode=mode,profile=profile,research_stress_permitted=True);allow(row,fraction)
    row=facts("two_losses_half_normal",equity=100.);row["loss_streak"]=2;allow(row,.01)
    row=facts("two_losses_half_aggressive",equity=100.);row.update(loss_streak=2,requested_mode="AGGRESSIVE");allow(row,.0175)
    for level in (1,2):
        row=facts("two_losses_half_add_"+str(level),equity=100.)
        row.update(loss_streak=2,campaign_count=1,adds=level-1,base_open=True,base_breakeven_confirmed=True,
          earlier_breakeven_confirmed=True,all_legs_profitable=True,campaign_nominal_risk=2.,current_open_risk=.2,
          closed_gain_r=float(level))
        allow(row,.0075 if level==1 else .005,level)
    for side in (1,-1):
        for level in (1,2):
            row=facts(("long" if side==1 else "short")+"_winner_add_"+str(level),equity=100.,side=side)
            row.update(campaign_count=1,adds=level-1,base_open=True,base_breakeven_confirmed=True,
              earlier_breakeven_confirmed=True,all_legs_profitable=True,campaign_nominal_risk=2.,
              current_open_risk=.2,closed_gain_r=float(level),consensus=side*(78. if level==1 else 82.),orion=side*80.,nova=side*80.)
            allow(row,.015 if level==1 else .01,level)
    base=facts("base")
    for field,reason in [("capital_valid","capital_unverified"),("reconciled","reconciliation_or_ownership"),
      ("ownership_valid","reconciliation_or_ownership"),("signal_ready","mandatory_inputs_invalid"),
      ("news_valid","mandatory_inputs_invalid"),("macro_valid","mandatory_inputs_invalid"),
      ("session_valid","mandatory_inputs_invalid"),("quote_fresh","mandatory_inputs_invalid"),
      ("decision_fresh","mandatory_inputs_invalid"),("current_risk_valid","current_risk_unverified"),
      ("connected","connection_data_or_protection"),("data_fresh","connection_data_or_protection"),
      ("protection_confirmed","connection_data_or_protection")]:
        reject({**base,"case_id":field+"_false",field:False},reason)
    for name,changes,reason,mode in [
      ("pending_intent",dict(pending_intent=True),"reconciliation_or_ownership","FROZEN"),
      ("news_blackout",dict(news_blocked=True),"mandatory_inputs_invalid","FROZEN"),
      ("persistent_freeze",dict(persistent_frozen=True),"three_losses","FROZEN"),
      ("three_losses",dict(loss_streak=3),"three_losses","FROZEN"),
      ("daily_kill_persists",dict(daily_killed=True),"daily_drawdown_15","KILL"),
      ("exact_dd_15_cash",dict(equity=42.5),"daily_drawdown_15","KILL"),
      ("exact_dd_10_cash",dict(equity=45.,requested_mode="EXTREME"),"extreme_disabled","FROZEN"),
      ("two_losses_extreme",dict(loss_streak=2,requested_mode="EXTREME"),"extreme_disabled","FROZEN"),
      ("extreme_disable_persists",dict(extreme_disabled=True,requested_mode="EXTREME"),"extreme_disabled","FROZEN"),
      ("stress_not_authorized",dict(profile="STRESS_10"),"offline_stress_only","FROZEN"),
      ("unknown_profile",dict(profile="OTHER"),"invalid_profile","FROZEN"),
      ("multiple_campaigns",dict(campaign_count=2),"campaign_state_invalid","FROZEN"),
      ("base_has_open_risk",dict(current_open_risk=.1),"campaign_state_invalid","FROZEN"),
      ("negative_open_risk",dict(current_open_risk=-.1),"current_risk_unverified","FROZEN"),
      ("unknown_open_risk",dict(current_open_risk=float("nan")),"current_risk_unverified","FROZEN"),
      ("atr_missing",dict(atr_m15=float("nan")),"actual_spread_gate","FROZEN"),
      ("spread_zero",dict(spread_price=0.),"actual_spread_gate","FROZEN"),
      ("spread_above_atr",dict(spread_price=.03001),"actual_spread_gate","FROZEN"),
      ("stop_too_close_atr",dict(atr_m15=.5),"stop_exceeds_atr_cap","FROZEN"),
      ("stop_too_far_atr",dict(atr_m15=.2),"stop_exceeds_atr_cap","FROZEN"),
      ("stop_inside_spread",dict(liquidation_price=1999.4),"stop_inside_spread_or_limit","FROZEN"),
      ("liquidation_wrong_side",dict(liquidation_price=2000.1),"stop_inside_spread_or_limit","FROZEN"),
      ("max_margin_missing",dict(max_margin_fraction=float("nan")),"invalid_risk_input","FROZEN"),
      ("max_margin_above_one",dict(max_margin_fraction=1.1),"invalid_risk_input","FROZEN"),
      ("used_margin_missing",dict(used_margin=float("nan")),"margin_allocation_unverified","FROZEN"),
      ("used_margin_negative",dict(used_margin=-1.),"margin_allocation_unverified","FROZEN"),
      ("margin_allocation_unverified",dict(margin_allocation_valid=False),"margin_allocation_unverified","FROZEN")]:
        reject({**base,**changes,"case_id":name},reason,mode)
    winner=facts("winner",equity=100.)
    winner.update(campaign_count=1,base_open=True,base_breakeven_confirmed=True,
      earlier_breakeven_confirmed=True,all_legs_profitable=True,campaign_nominal_risk=2.,current_open_risk=.2,
      closed_gain_r=2.,consensus=82.,orion=80.,nova=80.)
    for name,changes,reason in [
      ("max_two_adds",dict(adds=2),"add_limit_or_direction"),
      ("opposite_add",dict(campaign_side=-1),"add_limit_or_direction"),
      ("unknown_campaign_start",dict(campaign_starting_equity=float("nan")),"add_limit_or_direction"),
      ("zero_nominal_active_campaign",dict(campaign_nominal_risk=0.),"add_limit_or_direction"),
      ("base_already_closed",dict(base_open=False),"base_closed_no_add"),
      ("unknown_closed_gain",dict(closed_gain_r=float("nan")),"winner_inputs_invalid"),
      ("consensus_outside_score_domain",dict(consensus=1000.),"winner_inputs_invalid"),
      ("orion_outside_score_domain",dict(adds=1,orion=1000.),"winner_inputs_invalid"),
      ("nova_outside_score_domain",dict(adds=1,nova=-1000.),"winner_inputs_invalid"),
      ("first_gain_below_one",dict(closed_gain_r=.99999),"winner_threshold_not_met"),
      ("first_consensus_below_78",dict(consensus=77.99999),"winner_threshold_not_met"),
      ("second_gain_below_two",dict(adds=1,closed_gain_r=1.99999),"winner_threshold_not_met"),
      ("second_consensus_below_82",dict(adds=1,consensus=81.99999),"winner_threshold_not_met"),
      ("no_add_to_loser",dict(all_legs_profitable=False),"loser_add_forbidden"),
      ("base_be_unconfirmed",dict(base_breakeven_confirmed=False),"breakeven_not_confirmed"),
      ("earlier_be_unconfirmed",dict(adds=1,earlier_breakeven_confirmed=False),"breakeven_not_confirmed"),
      ("second_orion_below_80",dict(adds=1,orion=79.99999),"second_add_votes"),
      ("second_nova_below_80",dict(adds=1,nova=79.99999),"second_add_votes"),
      ("nominal_cap",dict(campaign_nominal_risk=7.),"campaign_nominal_cap"),
      ("open_risk_cap",dict(current_open_risk=7.),"campaign_open_risk_cap"),
      ("aggregate_margin_cap",dict(used_margin=24.,free_margin=76.,margin_per_lot=500.),"margin"),
      ("stress_base_spent_cap",dict(profile="STRESS_075",research_stress_permitted=True,campaign_nominal_risk=7.5),"campaign_nominal_cap")]:
        reject({**winner,**changes,"case_id":name},reason)
    return cases


def stop_cases():
    cases=[]
    for name,changes in [
      ("long_minimum_14_atr",{}),("short_minimum_14_atr",dict(side=-1,structural_stop=2000.5)),
      ("long_structure_wider",dict(structural_stop=1998.)),
      ("short_structure_wider",dict(side=-1,structural_stop=2002.)),
      ("long_structure_crossed_entry",dict(structural_stop=2000.1)),
      ("short_structure_crossed_entry",dict(side=-1,structural_stop=1999.9)),
      ("long_cap_exact",dict(structural_stop=1997.8)),
      ("short_cap_exact",dict(side=-1,structural_stop=2002.2)),
      ("long_cap_exceeded",dict(structural_stop=1997.799)),
      ("short_cap_exceeded",dict(side=-1,structural_stop=2002.201)),
      ("adverse_fill",dict(entry=2000.03)),
      ("rounding_exceeds_cap",dict(entry=2000.0001,structural_stop=1997.8001)),
      ("atr_zero",dict(atr=0.)),("atr_missing",dict(atr=float("nan"))),
      ("invalid_side",dict(side=0)),("tick_zero",dict(tick_size=0.)),
      ("structure_missing",dict(structural_stop=float("nan")))]:
        row=dict(case_id=name,entry=2000.,structural_stop=1999.5,atr=1.,side=1,tick_size=.001);row.update(changes)
        expected=dict(allowed=False,reason="invalid_stop",stop=0.)
        if all(math.isfinite(row[k]) and row[k]>0 for k in ("entry","structural_stop","atr","tick_size")) and row["side"] in (-1,1):
            raw=min(row["structural_stop"],row["entry"]-1.4*row["atr"]) if row["side"]==1 else max(row["structural_stop"],row["entry"]+1.4*row["atr"])
            stop=tick_price(raw,row["tick_size"],up=row["side"]==-1)
            if .35*row["atr"]<=row["side"]*(row["entry"]-stop)<=2.2*row["atr"]+1e-8:
                expected=dict(allowed=True,reason="PASS",stop=stop)
            else:expected["reason"]="stop_exceeds_atr_cap"
        cases.append((row,expected,"SPEC_stop_policy_with_frozen_tick_price"))
    return cases


def generate(output):
    output=Path(output).resolve()
    if output==REPO or REPO in output.parents:raise ValueError("synthetic output must be outside repository")
    output.mkdir(parents=True,exist_ok=False)
    (output/"fixture_kind.txt").write_text(KIND+"\n",encoding="ascii")
    collections={"size":size_cases(),"gate":gate_cases(),"campaign":campaign_cases(),"stop":stop_cases()}
    manifest={"fixture_kind":KIND,"core_version":CORE_VERSION,"harness_version":HARNESS_VERSION,
              "reference_sha256":{p:hashlib.sha256((REPO/p).read_bytes()).hexdigest() for p in REFERENCES},
              "families":{},"strategy_approval":False,"actual_native_run":False}
    for name,cases in collections.items():
        if not cases:raise ValueError("fixture family incomplete: "+name)
        inputs,outputs=TABLES[name]
        write(output/f"risk_{name}_cases.csv",inputs,[row for row,_,_ in cases])
        write(output/f"expected_risk_{name}_results.csv",outputs,[dict(expected,case_id=row["case_id"]) for row,expected,_ in cases])
        manifest["families"][name]={"cases":len(cases),"oracle_scope":{row["case_id"]:kind for row,_,kind in cases}}
    manifest["files"]={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.iterdir())}
    (output/"risk_reference_manifest.json").write_text(json.dumps(manifest,indent=2,allow_nan=False)+"\n")
    return manifest


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("output",type=Path)
    args=parser.parse_args();value=generate(args.output)
    print(json.dumps({"fixture_kind":KIND,"families":value["families"],"native_run":False},indent=2))
