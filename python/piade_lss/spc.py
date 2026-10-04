"""Statistical Quality Control: control charts, run rules, capability, sigma level."""
from __future__ import annotations
import math
import numpy as np
import pandas as pd
from scipy import stats
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)

D2_MR = 1.128        # d2 for moving range of 2
D4_MR = 3.267        # D4 for moving range of 2


def imr(x: pd.Series, phase1_mask: pd.Series | None = None) -> dict:
    """Individuals & Moving Range chart. Limits from Phase I if a mask is given."""
    base = x[phase1_mask] if phase1_mask is not None else x
    mr_base = base.diff().abs().dropna()
    cl, mrbar = base.mean(), mr_base.mean()
    sigma = mrbar / D2_MR
    return {"x": x, "mr": x.diff().abs(), "cl": cl, "ucl": cl + 3 * sigma, "lcl": cl - 3 * sigma,
            "sigma": sigma, "mr_cl": mrbar, "mr_ucl": D4_MR * mrbar}


def c4(n: int) -> float:
    return math.sqrt(2 / (n - 1)) * math.exp(math.lgamma(n / 2) - math.lgamma((n - 1) / 2))


def xbar_s(df: pd.DataFrame, value: str, group: str, phase1_mask=None) -> pd.DataFrame:
    """X-bar & S chart with variable subgroup size (limits recomputed per subgroup n)."""
    g = df.groupby(group)[value].agg(["mean", "std", "count"]).rename(columns={"count": "n"})
    g = g[g["n"] >= 2]
    base = g if phase1_mask is None else g[phase1_mask.reindex(g.index).fillna(False)]
    xbarbar = (base["mean"] * base["n"]).sum() / base["n"].sum()
    sbar = base["std"].mean()
    out = g.copy()
    c4n = out["n"].apply(c4)
    a3 = 3 / (c4n * np.sqrt(out["n"]))
    k = 3 * np.sqrt(1 - c4n ** 2) / c4n
    out["x_cl"], out["x_ucl"], out["x_lcl"] = xbarbar, xbarbar + a3 * sbar, xbarbar - a3 * sbar
    out["s_cl"], out["s_ucl"], out["s_lcl"] = sbar, (1 + k) * sbar, np.maximum(0, 1 - k) * sbar
    return out


def laney(defects: pd.Series, n: pd.Series, kind: str = "p", phase1_mask=None) -> pd.DataFrame:
    """Laney p' / u' chart: corrects over-dispersion that makes classic p/u limits useless with huge n."""
    rate = defects / n
    b = (slice(None) if phase1_mask is None else phase1_mask)
    pbar = defects[b].sum() / n[b].sum()
    sd_i = np.sqrt(pbar * (1 - pbar) / n) if kind == "p" else np.sqrt(pbar / n)
    z = (rate - pbar) / sd_i
    sigma_z = z[b].diff().abs().mean() / D2_MR
    out = pd.DataFrame({"rate": rate, "n": n, "cl": pbar})
    out["ucl_classic"], out["lcl_classic"] = pbar + 3 * sd_i, np.maximum(0, pbar - 3 * sd_i)
    out["ucl"], out["lcl"] = pbar + 3 * sd_i * sigma_z, np.maximum(0, pbar - 3 * sd_i * sigma_z)
    out.attrs["sigma_z"] = sigma_z
    return out


def western_electric(x: pd.Series, cl: float, sigma: float) -> pd.DataFrame:
    """Flag WE rules 1-4 (beyond 3s; 2/3 beyond 2s; 4/5 beyond 1s; 8 in a row one side)."""
    z = (x - cl) / sigma
    r1 = z.abs() > 3
    r2 = pd.Series(False, index=x.index)
    r3 = pd.Series(False, index=x.index)
    for side in (1, -1):
        r2 |= ((side * z) > 2).astype(int).rolling(3).sum() >= 2
        r3 |= ((side * z) > 1).astype(int).rolling(5).sum() >= 4
    s = np.sign(z)
    r4 = (s.rolling(8).sum().abs() == 8)
    return pd.DataFrame({"rule1": r1, "rule2": r2 & ~r1, "rule3": r3, "rule4": r4})


def capability(x: pd.Series, lsl=None, usl=None, sigma_within=None) -> dict:
    """Pp/Ppk (overall), Cpk (within, if sigma given) and percentile-based Ppk for non-normal data."""
    x = x.dropna()
    mu, s = x.mean(), x.std(ddof=1)
    res = {"n": len(x), "mean": mu, "std_overall": s}
    ad = stats.anderson(x, dist="norm")
    res["anderson_darling_A2"] = ad.statistic
    res["normal_at_5pct"] = bool(ad.statistic < ad.critical_values[2])
    ppk = []
    if lsl is not None:
        ppk.append((mu - lsl) / (3 * s))
        res["pct_below_lsl"] = (x < lsl).mean()
        res["ppk_percentile_lower"] = (x.median() - lsl) / (x.median() - x.quantile(0.00135))
    if usl is not None:
        ppk.append((usl - mu) / (3 * s))
        res["pct_above_usl"] = (x > usl).mean()
    res["ppk"] = min(ppk) if ppk else np.nan
    if sigma_within:
        cpk = []
        if lsl is not None: cpk.append((mu - lsl) / (3 * sigma_within))
        if usl is not None: cpk.append((usl - mu) / (3 * sigma_within))
        res["cpk"] = min(cpk)
    return res


def sigma_level(defects: float, opportunities: float, shift: float = 1.5) -> dict:
    dpmo = defects / opportunities * 1e6
    yld = 1 - defects / opportunities
    return {"DPMO": dpmo, "yield": yld, "sigma_level_short_term": stats.norm.ppf(yld) + shift}
