"""Frozen partition and evidence policy. No fitting or parameter selection."""
import math
import pandas as pd

RISKS=(.02,.035,.05,.075,.10)
PROFILES={
    'mode_cap_2pct':dict(risk_fraction=.02,extreme_risk=.05,max_campaign_risk_fraction=.075),
    'mode_cap_3_5pct':dict(risk_fraction=.035,extreme_risk=.05,max_campaign_risk_fraction=.075),
    'baseline_modes_2_3_5_5pct':dict(risk_fraction=.05,extreme_risk=.05,max_campaign_risk_fraction=.075),
    'stress_extreme_7_5pct_NONDEPLOYABLE':dict(risk_fraction=.075,extreme_risk=.075,max_campaign_risk_fraction=.075),
    'stress_extreme_10pct_NONDEPLOYABLE':dict(risk_fraction=.10,extreme_risk=.10,max_campaign_risk_fraction=.10),
}
COSTS={
    'baseline_assumptions':dict(spread_multiplier=1.,slippage_per_ounce=.03,
        commission_per_lot_per_side=0.,swap_long_per_lot_per_day=-53.49,swap_short_per_lot_per_day=0.),
    'stress_sensitivity':dict(spread_multiplier=2.,slippage_per_ounce=.10,
        commission_per_lot_per_side=3.5,swap_long_per_lot_per_day=-106.98,swap_short_per_lot_per_day=-5.),
}

def partitions(index):
    start=index[0].normalize();end=index[-1].normalize()+pd.Timedelta(days=1)
    days=(end-start).days
    if days < 100:raise ValueError('at least100 calendar days required for frozen protocol')
    a=start+pd.Timedelta(days=math.floor(days*.6))
    b=a+pd.Timedelta(days=math.floor(days*.2))
    result={
        'full_descriptive':dict(start=start,end=end,role='overlapping_descriptive'),
        'in_sample':dict(start=start,end=a,role='retrospective_IS'),
        'validation':dict(start=a,end=b,role='retrospective_validation'),
        'oos_previously_seen':dict(start=b,end=end,role='retrospective_OOS_NOT_unseen'),
    }
    at=start+pd.Timedelta(days=60);fold=1
    while at+pd.Timedelta(days=20) <= end:
        result[f'walk_forward_{fold:02}']=dict(start=at,end=at+pd.Timedelta(days=20),
             role='retrospective_walk_forward_test_NOT_unseen',train_start=start,train_end=at,
             fitting='none; unchanged frozen rules; expanding warmup history')
        at+=pd.Timedelta(days=20);fold+=1
    return result


def promotion_assessment(summaries, genuine_unseen=False, external_complete=False,
                         broker_cost_history_verified=False, evidence=None):
    reasons=[]
    if not genuine_unseen:reasons.append('no_genuine_unseen_evaluation')
    if not external_complete:reasons.append('mandatory_point_in_time_news_or_macro_missing')
    if not broker_cost_history_verified:reasons.append('historical_broker_cost_schedule_unverified')
    if evidence is None:
        reasons.append('no_unseen_100_campaign_60_day_bootstrap_and_walkforward_evidence')
    else:
        required={'campaigns','trading_days','expectancy_ci95','baseline_pf','stress_pf',
                  'max_drawdown','safety_failures','positive_walkforward_fraction'}
        if not required.issubset(evidence) or any(evidence[k] is None for k in required):
            reasons.append('incomplete_statistical_evidence')
        elif (evidence['campaigns'] < 100 or evidence['trading_days'] < 60 or
              evidence['expectancy_ci95'][0] <= 0 or evidence['baseline_pf'] <= 1.2 or
              evidence['stress_pf'] <= 1 or evidence['max_drawdown'] > .15 or
              evidence['safety_failures'] != 0 or evidence['positive_walkforward_fraction'] < 2/3):
            reasons.append('minimum_review_criteria_failed')
    return dict(status='NOT_EVALUABLE' if reasons else 'ELIGIBLE_FOR_HUMAN_REVIEW',forward_demo_trading_enabled=False,
                real_trading_enabled=False,reasons=reasons,
                statement='software mechanics tests are not strategy validation')
