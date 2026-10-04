"""Measure + Analyze: loss tree, Pareto, reliability, hypothesis tests, regression, data-driven FMEA."""
from __future__ import annotations
import numpy as np
import pandas as pd
from scipy import stats
import statsmodels.formula.api as smf
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)
from . import config as cfg


# ---------------------------------------------------------------- OEE / loss tree
def oee_summary(daily: pd.DataFrame, by="equipment_ID") -> pd.DataFrame:
    cols = ["logged_s", "scheduled_downtime_s", "planned_s", "run_s", "downtime_s", "idle_s",
            "performance_loss_s", "production_s", "units_in", "units_out", "ideal_run_units", "rejects"]
    t = daily.groupby(by)[cols].sum() if by else daily[cols].sum().to_frame("Fleet").T
    t["availability"] = t["run_s"] / t["planned_s"]
    t["performance"] = t["units_in"] / t["ideal_run_units"]
    t["quality"] = t["units_out"] / t["units_in"]
    t["oee"] = t["availability"] * t["performance"] * t["quality"]
    t["utilization"] = t["run_s"] / t["logged_s"]           # run time / logged time (TEEP-style on logged hours)
    return t


def loss_tree(daily: pd.DataFrame, enriched: pd.DataFrame, events: pd.DataFrame, top_n: int = 5) -> pd.DataFrame:
    """Hierarchical time-loss tree in hours (Logged -> Planned -> Run -> Net run -> Fully productive)."""
    s = oee_summary(daily, by=None).iloc[0]
    H = lambda v: v / 3600.0
    run_h = H(s.run_s)
    net_run_h = run_h * min(s.performance, 1.0)
    full_h = net_run_h * s.quality
    pl = enriched[enriched["type"] == "performance_loss"]
    eff_pl = pl["d_in"].sum() / pl["ideal_units"].sum()
    pl_loss = H(s.performance_loss_s) * (1 - eff_pl)
    sd = enriched[enriched["type"] == "scheduled_downtime"]["elapsed_s"]
    co = sd[(sd >= cfg.CHANGEOVER_MIN_S) & (sd <= cfg.CHANGEOVER_MAX_S)].sum()
    long_ = sd[sd > cfg.CHANGEOVER_MAX_S].sum()
    ev = events.groupby("alarm")["duration_s"].sum().sort_values(ascending=False)
    rows = [
        ("0", "Logged time", None, H(s.logged_s)),
        ("1", "Scheduled downtime (planned stops)", "0", H(s.scheduled_downtime_s)),
        ("1.1", "Changeover / cleaning-like stops (10 min - 4 h)", "1", H(co)),
        ("1.2", "Long planned shutdowns (> 4 h)", "1", H(long_)),
        ("1.3", "Short planned stops (< 10 min)", "1", H(s.scheduled_downtime_s - co - long_)),
        ("2", "Planned production time", "0", H(s.planned_s)),
        ("2.1", "Availability loss: alarm downtime", "2", H(s.downtime_s)),
    ]
    for i, (a, v) in enumerate(ev.head(top_n).items(), 1):
        rows.append((f"2.1.{i}", f"Alarm {a}", "2.1", H(v)))
    rows += [
        (f"2.1.{top_n+1}", f"Other {len(ev)-top_n} alarms", "2.1", H(ev.iloc[top_n:].sum())),
        ("2.2", "Availability loss: idle (no reason code)", "2", H(s.idle_s)),
        ("3", "Run time", "2", run_h),
        ("3.1", "Performance loss: reduced-speed / minor-stop state", "3", pl_loss),
        ("3.2", "Performance loss: sub-rated running in production state", "3", run_h - net_run_h - pl_loss),
        ("4", "Net run time", "3", net_run_h),
        ("4.1", "Quality loss: rejected packages", "4", net_run_h - full_h),
        ("5", "Fully productive time (= OEE x planned time)", "4", full_h),
    ]
    t = pd.DataFrame(rows, columns=["node", "name", "parent", "hours"])
    t["pct_of_planned"] = t["hours"] / H(s.planned_s)
    return t


# ---------------------------------------------------------------- Pareto
def pareto(events: pd.DataFrame, metric: str = "hours", machine: str | None = None) -> pd.DataFrame:
    ev = events if machine is None else events[events["equipment_ID"] == machine]
    p = ev.groupby("alarm").agg(stops=("duration_s", "size"), hours=("duration_s", lambda x: x.sum() / 3600),
                                mttr_min=("duration_s", lambda x: x.mean() / 60),
                                median_min=("duration_s", lambda x: x.median() / 60),
                                machines=("equipment_ID", "nunique"))
    p = p.sort_values(metric, ascending=False)
    p["share"] = p[metric] / p[metric].sum()
    p["cum_share"] = p["share"].cumsum()
    p["class"] = np.where(p["cum_share"].shift(fill_value=0) < 0.80, "A (vital few)", np.where(p["cum_share"].shift(fill_value=0) < 0.95, "B", "C (useful many)"))
    return p.reset_index()


def reliability(daily: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    run_h = daily.groupby("equipment_ID")["run_s"].sum() / 3600
    e = events.groupby("equipment_ID").agg(stops=("duration_s", "size"), down_h=("duration_s", lambda x: x.sum() / 3600))
    e["run_h"] = run_h
    e["MTBF_min"] = e["run_h"] / e["stops"] * 60
    e["MTTR_min"] = e["down_h"] / e["stops"] * 60
    e["inherent_availability"] = e["MTBF_min"] / (e["MTBF_min"] + e["MTTR_min"])
    e["stops_per_run_hour"] = e["stops"] / e["run_h"]
    return e


# ---------------------------------------------------------------- hypothesis tests
def _row(name, h0, stat, p, note):
    return {"test": name, "H0": h0, "statistic": stat, "p_value": p,
            "decision (alpha=0.05)": "Reject H0" if p < 0.05 else "Fail to reject H0", "interpretation": note}


def hypothesis_tests(daily: pd.DataFrame, enriched: pd.DataFrame) -> pd.DataFrame:
    out = []
    d = daily.dropna(subset=["oee"])
    ad = stats.anderson(d["oee"], dist="norm")
    out.append(_row("Anderson-Darling normality (daily OEE)", "Daily OEE is normally distributed", ad.statistic,
                    0.001 if ad.statistic > ad.critical_values[-1] else 0.2,
                    "Non-normal -> use non-parametric tests and percentile capability"))
    groups = [g["oee"].values for _, g in d.groupby("equipment_ID")]
    h, p = stats.kruskal(*groups)
    out.append(_row("Kruskal-Wallis: OEE by machine", "Median daily OEE equal across s_1..s_5", h, p,
                    "Machines behave as different processes -> stratify, don't pool"))
    # shift-level shares
    sh = enriched.groupby(["equipment_ID", enriched["ts"].dt.date, "shift", "type"])["elapsed_s"].sum().unstack(fill_value=0)
    sh = sh.div(sh.sum(axis=1), axis=0).reset_index()
    for col, label in [("idle", "idle share"), ("downtime", "alarm-downtime share")]:
        gs = [g[col].values for _, g in sh.groupby("shift")]
        h, p = stats.kruskal(*gs)
        med = sh.groupby("shift")[col].mean().round(3).to_dict()
        out.append(_row(f"Kruskal-Wallis: {label} by shift", f"{label} equal across shifts", h, p, f"Mean by shift: {med}"))
    wk = d.assign(weekend=d["date"].dt.dayofweek >= 5)
    idle_share = wk["idle_s"] / wk["planned_s"].replace(0, np.nan)
    a, b = idle_share[wk["weekend"]].dropna(), idle_share[~wk["weekend"]].dropna()
    u, p = stats.mannwhitneyu(a, b, alternative="greater")
    out.append(_row("Mann-Whitney: weekend vs weekday idle share", "Weekend idle share <= weekday", u, p,
                    f"Median weekend {a.median():.1%} vs weekday {b.median():.1%}"))
    y20, y21 = d[d["date"].dt.year == 2020]["oee"], d[d["date"].dt.year == 2021]["oee"]
    u, p = stats.mannwhitneyu(y20, y21, alternative="two-sided")
    out.append(_row("Mann-Whitney: OEE 2020 vs 2021", "No shift in OEE between years", u, p,
                    f"Median 2020 {y20.median():.1%} vs 2021 {y21.median():.1%}"))
    ct = pd.crosstab(enriched.loc[enriched["type"] == "downtime", "shift"],
                     enriched.loc[enriched["type"] == "downtime", "alarm"].where(lambda x: x.isin(["A_065", "A_101", "A_006", "A_001"]), "other"))
    chi2, p, dof, _ = stats.chi2_contingency(ct)
    out.append(_row("Chi-square: top-alarm mix vs shift", "Alarm mix independent of shift", chi2, p,
                    f"dof={dof}; Cramer's V={np.sqrt(chi2 / (ct.values.sum() * (min(ct.shape) - 1))):.3f} (effect size)"))
    return pd.DataFrame(out)


def regression(seq: pd.DataFrame, top_alarms: list[str]) -> tuple[pd.DataFrame, dict]:
    """Two OLS models on the hourly sequences (HC3 robust SE, machine fixed effects).

    M1  pct_downtime   ~ stop counts of top alarms  -> coef x 60 = minutes of downtime per stop
    M2  pct_production ~ n_changes                   -> cost of process instability (state switching)
    """
    s = seq.copy().rename(columns={"#changes": "n_changes", "%production": "pct_production",
                            "%downtime": "pct_downtime", "count_sum": "alarm_count"}).copy()
    s.columns = [c.replace("/", "_") for c in s.columns]
    s = s.copy()
    acols = [c for c in s.columns if c.startswith("A_")]
    s[acols] = s[acols].fillna(0)                 # NaN = alarm code not present on that machine
    top = [a for a in top_alarms if a in s.columns]
    s["other_alarms"] = s["alarm_count"] - s[top].sum(axis=1)
    rows, info = [], {}
    specs = {"M1": "pct_downtime ~ " + " + ".join(top + ["other_alarms", "C(equipment_ID)"]),
             "M2": "pct_production ~ n_changes + C(equipment_ID)"}
    for k, f in specs.items():
        m = smf.ols(f, data=s).fit(cov_type="HC3")
        ci = m.conf_int()
        for t in m.params.index:
            rows.append({"model": k, "term": t, "coef": m.params[t], "std_err": m.bse[t], "p_value": m.pvalues[t],
                         "ci_low": ci.loc[t, 0], "ci_high": ci.loc[t, 1]})
        info[k] = {"formula": f, "r2": m.rsquared, "adj_r2": m.rsquared_adj, "n": int(m.nobs)}
    coef = pd.DataFrame(rows)
    coef["minutes_per_stop"] = np.where((coef["model"] == "M1") & (coef["term"].str.startswith("A_") | (coef["term"] == "other_alarms")), coef["coef"] * 60, np.nan)
    return coef, info


# ---------------------------------------------------------------- FMEA
def _bin(v, edges):
    return int(np.searchsorted(edges, v, side="right") + 1)


def fmea(events: pd.DataFrame, daily: pd.DataFrame, top_n: int = 10) -> pd.DataFrame:
    """Data-driven FMEA. S from MTTR, O from stops per 1000 run-hours, D from 'repeat within 30 min' rate."""
    ev = events.sort_values(["equipment_ID", "ts"]).copy()
    ev["prev_same_gap"] = ev.groupby(["equipment_ID", "alarm"])["ts"].diff().dt.total_seconds()
    run_h = daily.groupby("equipment_ID")["run_s"].sum() / 3600
    p = pareto(events).head(top_n)
    rows = []
    for a in p["alarm"]:
        e = ev[ev["alarm"] == a]
        mach = e["equipment_ID"].unique()
        rate = len(e) / run_h[mach].sum() * 1000
        mttr = e["duration_s"].mean() / 60
        repeat = (e["prev_same_gap"] <= 1800).mean()
        S = _bin(mttr, [0.5, 1, 2, 3, 5, 10, 20, 60, 120])
        O = _bin(rate, [1, 3, 10, 30, 100, 300, 1000, 3000, 10000])
        D = int(np.clip(round(10 - 8 * repeat), 2, 10))   # frequent repeats = the failure 'announces itself'
        rows.append({"failure_mode": a, "machines": ", ".join(sorted(mach)), "downtime_h": e["duration_s"].sum() / 3600,
                     "stops": len(e), "MTTR_min": mttr, "stops_per_1000_run_h": rate, "repeat_within_30min": repeat,
                     "S": S, "O": O, "D": D, "RPN": S * O * D})
    f = pd.DataFrame(rows).sort_values("RPN", ascending=False)
    f["action_priority"] = np.where(f["RPN"] >= 200, "High", np.where(f["RPN"] >= 120, "Medium", "Low"))
    return f
