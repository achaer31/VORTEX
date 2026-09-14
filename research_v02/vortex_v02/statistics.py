"""Descriptive statistics and fixed-seed moving-block bootstrap, not a guarantee."""
import numpy as np

def campaign_metrics(pnl, trading_days=0, seed=20260914, samples=2000, block_size=5):
    x=np.asarray(pnl,dtype=float)
    if x.ndim != 1 or not np.isfinite(x).all():raise ValueError('finite campaign P/L required')
    n=len(x)
    if n == 0:
        return dict(campaigns=0,expectancy=None,profit_factor=None,win_rate=None,
                    expectancy_ci95=None,trading_days=trading_days,sufficient_sample=False)
    gains=float(x[x>0].sum());losses=float(-x[x<0].sum())
    ci=None
    if n >= 100 and trading_days >= 60:
        rng=np.random.default_rng(seed)
        means=[]
        for _ in range(samples):
            starts=rng.integers(0,n,size=int(np.ceil(n/block_size)))
            indices=np.concatenate([(s+np.arange(block_size)) % n for s in starts])[:n]
            means.append(float(x[indices].mean()))
        ci=[float(v) for v in np.quantile(means,[.025,.975])]
    return dict(campaigns=n,expectancy=float(x.mean()),profit_factor=gains/losses if losses else None,
                win_rate=float((x>0).mean()),expectancy_ci95=ci,trading_days=trading_days,
                sufficient_sample=ci is not None,bootstrap=dict(method='circular_moving_blocks',block_size=block_size,
                    samples=samples,seed=seed),profit_factor_undefined_no_losses=losses==0)
