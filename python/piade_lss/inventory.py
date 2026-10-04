"""Inventory optimisation: service-level based Safety Stock, Reorder Point, EOQ, Kanban sizing,
spare-parts policy, and an out-of-sample backtest of the (s, Q) policy on real consumption."""
from __future__ import annotations
import math
import numpy as np
import pandas as pd
from scipy import stats
from . import config as cfg


def daily_demand(daily: pd.DataFrame) -> pd.DataFrame:
    """Calendar-day packaging-material consumption per machine (1 blank per input package; zero-filled)."""
    out = []
    for m, g in daily.groupby("equipment_ID"):
        idx = pd.date_range(g["date"].min(), g["date"].max(), freq="D")
        s = g.set_index("date")["units_in"].reindex(idx, fill_value=0).rename("demand")
        out.append(s.to_frame().assign(equipment_ID=m).rename_axis("date").reset_index())
    return pd.concat(out, ignore_index=True)


def policy(mean_d, sd_d, L=cfg.PKG_LEAD_TIME_DAYS, sd_L=cfg.PKG_LEAD_TIME_SD_DAYS, sl=cfg.TARGET_SERVICE_LEVEL,
           unit_cost=cfg.PKG_UNIT_COST_INR, order_cost=cfg.ORDER_COST_INR, h_rate=cfg.HOLDING_RATE, days=365):
    """Continuous review (s, Q): SS = z*sqrt(L*sd_d^2 + d^2*sd_L^2); ROP = d*L + SS; EOQ = sqrt(2DS/H)."""
    z = stats.norm.ppf(sl)
    sigma_ltd = math.sqrt(L * sd_d ** 2 + (mean_d ** 2) * sd_L ** 2)
    ss = z * sigma_ltd
    D = mean_d * days
    H = unit_cost * h_rate
    eoq = math.sqrt(2 * D * order_cost / H) if D > 0 else 0
    return {"service_level": sl, "z": z, "mean_daily": mean_d, "sd_daily": sd_d, "sigma_LTD": sigma_ltd,
            "safety_stock": ss, "reorder_point": mean_d * L + ss, "EOQ": eoq, "annual_demand": D,
            "orders_per_year": D / eoq if eoq else 0, "avg_inventory": eoq / 2 + ss,
            "days_of_cover_avg": (eoq / 2 + ss) / mean_d if mean_d else np.nan,
            "annual_ordering_cost": (D / eoq) * order_cost if eoq else 0,
            "annual_holding_cost": H * (eoq / 2 + ss), "ss_holding_cost": H * ss}


def policy_table(demand: pd.DataFrame, train_end=cfg.PHASE1_END) -> pd.DataFrame:
    rows = []
    for m, g in demand.groupby("equipment_ID"):
        tr = g[g["date"] <= train_end]
        tr = tr if len(tr) >= 60 else g.iloc[: len(g) // 2]           # short Phase I -> use first half
        for sl in cfg.SERVICE_LEVELS:
            r = policy(tr["demand"].mean(), tr["demand"].std(ddof=1), sl=sl)
            # empirical lead-time-demand check (non-normal daily demand, many zero days)
            ltd = tr["demand"].rolling(cfg.PKG_LEAD_TIME_DAYS).sum().dropna()
            r["ss_empirical"] = max(ltd.quantile(sl) - ltd.mean(), 0)
            r["total_annual_cost"] = r["annual_ordering_cost"] + r["annual_holding_cost"]
            rows.append({"equipment_ID": m, "train_days": len(tr), **r})
    return pd.DataFrame(rows)


def backtest(demand: pd.DataFrame, pol: pd.DataFrame, sl=cfg.TARGET_SERVICE_LEVEL, n_sims=200, seed=7) -> pd.DataFrame:
    """Simulate the (ROP, EOQ) policy on the held-out 2021 demand with random lead times."""
    rng = np.random.default_rng(seed)
    res = []
    for m, g in demand.groupby("equipment_ID"):
        p = pol[(pol["equipment_ID"] == m) & (np.isclose(pol["service_level"], sl))].iloc[0]
        test = g[g["date"] > cfg.PHASE1_END]["demand"].to_numpy()
        if len(test) < 60:
            test = g.iloc[len(g) // 2:]["demand"].to_numpy()
        rop, q = p["reorder_point"], p["EOQ"]
        csl, fill, inv_avg = [], [], []
        for _ in range(n_sims):
            on_hand, pipeline, cycles, stockout_cycles, short, cycle_short = rop + q / 2, [], 0, 0, 0.0, False
            inv_trace = []
            for t, d in enumerate(test):
                arrived = [x for x in pipeline if x[0] == t]
                for a in arrived:
                    on_hand += a[1]; cycles += 1; stockout_cycles += cycle_short; cycle_short = False
                pipeline = [x for x in pipeline if x[0] != t]
                served = min(on_hand, d); short += d - served; on_hand -= served
                if d - served > 0: cycle_short = True
                position = on_hand + sum(x[1] for x in pipeline)
                if position <= rop:
                    lt = max(1, int(round(rng.normal(cfg.PKG_LEAD_TIME_DAYS, cfg.PKG_LEAD_TIME_SD_DAYS))))
                    pipeline.append((t + lt, q))
                inv_trace.append(on_hand)
            csl.append(1 - stockout_cycles / max(cycles, 1))
            fill.append(1 - short / max(test.sum(), 1))
            inv_avg.append(np.mean(inv_trace))
        res.append({"equipment_ID": m, "target_CSL": sl, "achieved_CSL": np.mean(csl), "fill_rate": np.mean(fill),
                    "avg_on_hand": np.mean(inv_avg), "test_days": len(test),
                    "test_mean_demand": test.mean(), "train_mean_demand": p["mean_daily"]})
    return pd.DataFrame(res)


def sample_path(demand: pd.DataFrame, pol: pd.DataFrame, machine="s_1", sl=cfg.TARGET_SERVICE_LEVEL, seed=11) -> pd.DataFrame:
    """One simulated inventory trajectory (for the saw-tooth chart)."""
    rng = np.random.default_rng(seed)
    p = pol[(pol["equipment_ID"] == machine) & (np.isclose(pol["service_level"], sl))].iloc[0]
    g = demand[(demand["equipment_ID"] == machine) & (demand["date"] > cfg.PHASE1_END)].reset_index(drop=True)
    rop, q, on_hand, pipeline, rows = p["reorder_point"], p["EOQ"], p["reorder_point"] + p["EOQ"] / 2, [], []
    for t, r in g.iterrows():
        on_hand += sum(x[1] for x in pipeline if x[0] == t)
        pipeline = [x for x in pipeline if x[0] != t]
        served = min(on_hand, r["demand"]); on_hand -= served
        if on_hand + sum(x[1] for x in pipeline) <= rop:
            pipeline.append((t + max(1, int(round(rng.normal(cfg.PKG_LEAD_TIME_DAYS, cfg.PKG_LEAD_TIME_SD_DAYS)))), q))
        rows.append({"date": r["date"], "demand": r["demand"], "on_hand": on_hand, "short": r["demand"] - served,
                     "rop": rop, "ss": p["safety_stock"]})
    return pd.DataFrame(rows)


def spare_parts(events: pd.DataFrame, alarms=("A_065", "A_001", "A_006")) -> pd.DataFrame:
    """Spare-kit policy for critical failure modes. ASSUMPTION: a stop >= 30 min consumes one kit.
    Weekly demand is Poisson -> exact Poisson ROP, compared with the normal approximation."""
    ev = events[events["duration_s"] >= cfg.SPARE_KIT_EVENT_MIN_S].copy()
    weeks = (events["ts"].max() - events["ts"].min()).days / 7
    Lw = cfg.SPARE_LEAD_TIME_DAYS / 7
    rows = []
    for a in alarms:
        n = (ev["alarm"] == a).sum()
        lam_w = n / weeks
        mu_L = lam_w * Lw
        rop_pois = int(stats.poisson.ppf(cfg.SPARE_SERVICE_LEVEL, mu_L))
        z = stats.norm.ppf(cfg.SPARE_SERVICE_LEVEL)
        rop_norm = mu_L + z * math.sqrt(mu_L)
        D = lam_w * 52
        H = cfg.SPARE_UNIT_COST_INR * cfg.SPARE_HOLDING_RATE
        eoq = math.sqrt(2 * D * cfg.SPARE_ORDER_COST_INR / H)
        rows.append({"failure_mode": a, "kit_events_2y": int(n), "weekly_rate": lam_w, "LTD_mean": mu_L,
                     "ROP_poisson": rop_pois, "SS_poisson": rop_pois - mu_L, "ROP_normal_approx": rop_norm,
                     "achieved_SL_poisson": stats.poisson.cdf(rop_pois, mu_L), "annual_demand": D,
                     "EOQ": eoq, "EOQ_rounded": max(1, round(eoq))})
    return pd.DataFrame(rows)


def kanban(daily: pd.DataFrame) -> pd.DataFrame:
    """N = D x L x (1 + alpha) / C, for average and peak (rated-speed) hourly draw."""
    t = daily.groupby("equipment_ID").agg(units=("units_in", "sum"), planned_h=("planned_s", lambda x: x.sum() / 3600),
                                           ideal=("ideal_run_units", "sum"), run_h=("run_s", lambda x: x.sum() / 3600))
    t["avg_draw_per_h"] = t["units"] / t["planned_h"]
    t["rated_draw_per_h"] = t["ideal"] / t["run_h"]
    f = cfg.KANBAN_REPLEN_HOURS * (1 + cfg.KANBAN_SAFETY_FACTOR) / cfg.KANBAN_CONTAINER_QTY
    t["kanbans_avg"] = np.ceil(t["avg_draw_per_h"] * f).astype(int)
    t["kanbans_peak"] = np.ceil(t["rated_draw_per_h"] * f).astype(int)
    t["container_qty"] = cfg.KANBAN_CONTAINER_QTY
    t["replenish_lead_h"] = cfg.KANBAN_REPLEN_HOURS
    t["line_side_max_units"] = t["kanbans_peak"] * cfg.KANBAN_CONTAINER_QTY
    return t.reset_index()


def ss_sensitivity(pol: pd.DataFrame, machine="s_1") -> pd.DataFrame:
    """How much safety stock falls if process stabilisation cuts daily-demand variability."""
    base = pol[(pol["equipment_ID"] == machine) & np.isclose(pol["service_level"], cfg.TARGET_SERVICE_LEVEL)].iloc[0]
    rows = []
    for k in [1.0, 0.9, 0.8, 0.7, 0.6]:
        r = policy(base["mean_daily"], base["sd_daily"] * k)
        rows.append({"sd_multiplier": k, "safety_stock": r["safety_stock"], "ss_holding_cost_INR": r["ss_holding_cost"]})
    return pd.DataFrame(rows)


def backtest_adaptive(demand: pd.DataFrame, sl=cfg.TARGET_SERVICE_LEVEL, window=90, n_sims=100, seed=7) -> pd.DataFrame:
    """Control-phase policy: re-estimate ROP/EOQ every month from a trailing window and use the larger of the
    normal-theory and empirical (bootstrapped lead-time-demand) safety stock."""
    rng = np.random.default_rng(seed)
    res = []
    for m, g in demand.groupby("equipment_ID"):
        g = g.reset_index(drop=True)
        start = g.index[g["date"] > cfg.PHASE1_END]
        start = start[0] if len(start) and start[0] >= 60 else len(g) // 2
        params = {}
        for t in range(start, len(g)):
            if t == start or g.loc[t, "date"].day == 1:
                w = g.loc[max(0, t - window):t - 1, "demand"]
                r = policy(w.mean(), w.std(ddof=1), sl=sl)
                ltd = w.rolling(cfg.PKG_LEAD_TIME_DAYS).sum().dropna()
                ss = max(r["safety_stock"], ltd.quantile(sl) - ltd.mean())
                cur = (w.mean() * cfg.PKG_LEAD_TIME_DAYS + ss, r["EOQ"])
            params[t] = cur
        test = g.loc[start:, "demand"].to_numpy()
        csl, fill, inv_avg = [], [], []
        for _ in range(n_sims):
            rop0, q0 = params[start]
            on_hand, pipeline, cycles, so, short, cyc_short, trace = rop0 + q0 / 2, [], 0, 0, 0.0, False, []
            for i, d in enumerate(test):
                rop, q = params[start + i]
                for a in [x for x in pipeline if x[0] == i]:
                    on_hand += a[1]; cycles += 1; so += cyc_short; cyc_short = False
                pipeline = [x for x in pipeline if x[0] != i]
                served = min(on_hand, d); short += d - served; on_hand -= served
                cyc_short |= (d - served) > 0
                if on_hand + sum(x[1] for x in pipeline) <= rop:
                    pipeline.append((i + max(1, int(round(rng.normal(cfg.PKG_LEAD_TIME_DAYS, cfg.PKG_LEAD_TIME_SD_DAYS)))), q))
                trace.append(on_hand)
            csl.append(1 - so / max(cycles, 1)); fill.append(1 - short / max(test.sum(), 1)); inv_avg.append(np.mean(trace))
        res.append({"equipment_ID": m, "target_CSL": sl, "achieved_CSL": np.mean(csl), "fill_rate": np.mean(fill),
                    "avg_on_hand": np.mean(inv_avg)})
    return pd.DataFrame(res)
