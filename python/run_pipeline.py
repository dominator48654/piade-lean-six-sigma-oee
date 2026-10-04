"""End-to-end DMAIC analytics pipeline for the PIADE packaging dataset.

Usage:  python run_pipeline.py            (expects data/raw_data.csv and data/sequences_1h_data.csv)
Outputs: outputs/tables/*.csv, outputs/figures/*.png, outputs/powerbi/*.csv, outputs/key_metrics.json
"""
from __future__ import annotations
import json
import numpy as np
import pandas as pd
from piade_lss import config as cfg, data as D, analysis as A, spc as S, inventory as I, lean as L, viz as V

TOP_ALARMS = ["A_065", "A_101", "A_006", "A_001", "A_066", "A_005", "A_020", "A_010"]
PILOT = "s_1"


def save(df: pd.DataFrame, name: str, index=False):
    cfg.TAB_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(cfg.TAB_DIR / f"{name}.csv", index=index)


def main():
    for p in (cfg.FIG_DIR, cfg.TAB_DIR, cfg.BI_DIR):
        p.mkdir(parents=True, exist_ok=True)
    km = {}

    # ---------------- MEASURE: data collection + integrity (MSA substitute)
    raw = D.load_raw()
    integ = D.integrity_report(raw); save(integ, "M00_data_integrity")
    e = D.enrich(raw)
    daily = D.daily_machine(e)
    events = D.downtime_events(e)
    seq = D.load_sequences()
    save(daily, "daily_machine")

    summ = A.oee_summary(daily); fleet = A.oee_summary(daily, by=None).iloc[0]
    save(pd.concat([summ, fleet.to_frame("Fleet").T]).reset_index().rename(columns={"index": "equipment_ID"}), "M01_oee_summary")
    tree = A.loss_tree(daily, e, events); save(tree, "M02_loss_tree")
    par_h = A.pareto(events, "hours"); save(par_h, "M03_pareto_hours")
    par_n = A.pareto(events, "stops"); save(par_n, "M04_pareto_stops")
    for m in cfg.MACHINES:
        save(A.pareto(events, "hours", m).head(10), f"M05_pareto_hours_{m}")
    rel = A.reliability(daily, events); save(rel, "M06_reliability", index=True)
    sig = S.sigma_level(fleet.rejects, fleet.units_in); km["sigma_rejects"] = sig
    km.update({"fleet_oee": fleet.oee, "fleet_A": fleet.availability, "fleet_P": fleet.performance, "fleet_Q": fleet.quality,
               "planned_hours": fleet.planned_s / 3600, "rows": len(raw), "stop_events": len(events), "alarm_codes": int(events["alarm"].nunique())})

    # ---------------- ANALYZE
    ht = A.hypothesis_tests(daily, e); save(ht, "A01_hypothesis_tests")
    coef, reg_info = A.regression(seq, TOP_ALARMS); save(coef, "A02_regression"); km["regression"] = reg_info
    fm = A.fmea(events, daily); save(fm, "A03_fmea")

    # ---------------- SPC on pilot machine (Phase I = 2020 limits, Phase II = 2021)
    sp = daily[(daily["equipment_ID"] == PILOT) & (daily["planned_s"] >= 4 * 3600)].set_index("date").sort_index()
    ph1 = sp.index <= cfg.PHASE1_END
    ch = S.imr(sp["oee"], pd.Series(ph1, index=sp.index))
    fl = S.western_electric(sp["oee"], ch["cl"], ch["sigma"])
    ch["ucl"] = min(ch["ucl"], 1.0)          # OEE has a natural upper bound of 100 %
    km["imr_pilot"] = {k: float(v) for k, v in ch.items() if np.isscalar(v)}
    km["imr_pilot"]["phase2_rule1"] = int(fl.loc[~ph1, "rule1"].sum()); km["imr_pilot"]["phase2_any_rule"] = int(fl.loc[~ph1].any(axis=1).sum())
    km["imr_pilot"]["phase2_days"] = int((~ph1).sum()); km["imr_pilot"]["phase2_mean"] = float(sp.loc[~ph1, "oee"].mean())
    save(pd.DataFrame({"oee": sp["oee"], "mr": ch["mr"], "cl": ch["cl"], "ucl": ch["ucl"], "lcl": ch["lcl"]}).join(fl).reset_index(), "C01_imr_pilot_oee")
    wk = sp.reset_index().assign(week=lambda d: d["date"].dt.to_period("W").dt.start_time)
    xs = S.xbar_s(wk, "oee", "week", pd.Series(wk.groupby("week")["date"].max() <= cfg.PHASE1_END)); save(xs.reset_index(), "C02_xbar_s_pilot")
    q = sp[sp["units_in"] > 1000]
    lp = S.laney(q["rejects"], q["units_in"], "p", pd.Series(q.index <= cfg.PHASE1_END, index=q.index)); save(lp.reset_index(), "C03_laney_p_rejects")
    km["laney_p_sigma_z"] = float(lp.attrs["sigma_z"])
    u = sp[sp["run_s"] > 3600]
    lu = S.laney(u["stop_events"], u["run_s"] / 3600, "u", pd.Series(u.index <= cfg.PHASE1_END, index=u.index)); save(lu.reset_index(), "C04_laney_u_stops")
    km["laney_u_sigma_z"] = float(lu.attrs["sigma_z"])
    cap_oee = S.capability(sp["oee"], lsl=cfg.OEE_TARGET, sigma_within=ch["sigma"])
    cap_q = S.capability(q["quality"], lsl=cfg.QUALITY_LSL)
    km["capability_oee_pilot"], km["capability_quality_pilot"] = cap_oee, cap_q
    days_below = (sp["oee"] < cfg.OEE_TARGET).sum()
    km["oee_day_sigma"] = S.sigma_level(days_below, len(sp))

    # ---------------- IMPROVE
    smed = L.smed_baseline(e); save(smed, "I01_smed_baseline")
    scen, fin = L.improvement_scenario(daily, events); save(scen, "I02_improvement_scenario"); km["financials"] = fin

    # ---------------- INVENTORY
    dem = I.daily_demand(daily); save(dem, "V00_daily_material_demand")
    pol = I.policy_table(dem); save(pol, "V01_inventory_policy")
    bt = I.backtest(dem, pol); bta = I.backtest_adaptive(dem)
    save(bt.merge(bta, on=["equipment_ID", "target_CSL"], suffixes=("_static", "_adaptive")), "V02_policy_backtest")
    spares = I.spare_parts(events); save(spares, "V03_spare_parts_policy")
    kb = I.kanban(daily); save(kb, "V04_kanban_sizing")
    sens = I.ss_sensitivity(pol, PILOT); save(sens, "V05_ss_sensitivity")
    path = I.sample_path(dem, pol, PILOT)

    vsm = L.vsm_data(daily, events, smed, pol, PILOT)
    # pilot future OEE: apply the same lever logic to the pilot machine only
    sc_p, fin_p = L.improvement_scenario(daily[daily["equipment_ID"] == PILOT], events[events["equipment_ID"] == PILOT])
    vsm["oee_future"] = float(fin_p["projected_oee"]); km["vsm_pilot"] = {k: (float(v) if not isinstance(v, str) else v) for k, v in vsm.items()}
    save(sc_p, "I03_pilot_improvement_scenario")

    # ---------------- FIGURES
    V.oee_by_machine(summ, fleet); V.loss_waterfall(tree); V.loss_tree_diagram(tree)
    V.pareto_chart(par_h, "hours", "M04_pareto_downtime_hours", "Pareto: alarm downtime hours (fleet)")
    V.pareto_chart(par_n, "stops", "M05_pareto_stop_frequency", "Pareto: number of alarm stops (fleet)")
    V.alarm_machine_heatmap(events, TOP_ALARMS); V.time_heatmaps(e); V.monthly_trend(daily); V.reliability_chart(rel)
    V.vsm(vsm, future=False); V.fishbone(); V.hypothesis_plots(daily, e); V.regression_plot(coef, reg_info); V.fmea_bubble(fm)
    V.smed_plot(e); V.improvement_bridge(scen); V.vsm(vsm, future=True)
    V.imr_chart(ch, fl, cfg.PHASE1_END, f"I-MR chart: daily OEE, {PILOT} (limits from Phase I = 2020)", "C01_imr_pilot_oee")
    V.xbar_s_chart(xs, f"X-bar chart: weekly mean of daily OEE, {PILOT}", "C02_xbar_s_pilot")
    V.laney_chart(lp, f"Laney p' chart: daily reject fraction, {PILOT}", "C03_laney_p_rejects", "Rejects (% of input)", 100)
    V.laney_chart(lu, f"Laney u' chart: alarm stops per run-hour, {PILOT}", "C04_laney_u_stops", "Stops / run-hour")
    V.capability_plot(sp["oee"], cap_oee, cfg.OEE_TARGET, f"Capability: daily OEE of {PILOT} vs LSL = target", "C05_capability_oee")
    V.inventory_tradeoff(pol); V.sawtooth(path, PILOT); V.backtest_plot(bt, bta)

    # ---------------- POWER BI star schema
    dim_date = pd.DataFrame({"date": pd.date_range(daily["date"].min(), daily["date"].max())})
    dim_date = dim_date.assign(year=dim_date.date.dt.year, month=dim_date.date.dt.month, month_name=dim_date.date.dt.strftime("%b"),
                               iso_week=dim_date.date.dt.isocalendar().week.astype(int), weekday=dim_date.date.dt.strftime("%a"),
                               is_weekend=dim_date.date.dt.dayofweek >= 5, phase=np.where(dim_date.date <= cfg.PHASE1_END, "Phase I (baseline)", "Phase II (monitor)"))
    dim_machine = raw.groupby("equipment_ID").agg(rated_speed_median=("speed", "median"), first_ts=("ts", "min"), last_ts=("ts", "max")).reset_index()
    dim_machine["is_pilot"] = dim_machine["equipment_ID"] == PILOT
    dim_alarm = par_h[["alarm", "class", "stops", "hours", "mttr_min"]].merge(fm[["failure_mode", "S", "O", "D", "RPN", "action_priority"]], left_on="alarm", right_on="failure_mode", how="left").drop(columns="failure_mode")
    fact_events = events.assign(date=events["ts"].dt.tz_localize(None).dt.floor("D"), hour=events["ts"].dt.hour, duration_min=events["duration_s"] / 60)
    fact_events = fact_events[["date", "hour", "shift", "equipment_ID", "alarm", "duration_min", "prev_type"]]
    fact_shift = e.groupby(["equipment_ID", e["ts"].dt.tz_localize(None).dt.floor("D").rename("date"), "shift", "type"])["elapsed_s"].sum().unstack(fill_value=0).reset_index()
    for n, df in {"dim_date": dim_date, "dim_machine": dim_machine, "dim_alarm": dim_alarm, "fact_daily_machine": daily,
                  "fact_downtime_events": fact_events, "fact_shift_state": fact_shift, "inventory_policy": pol,
                  "spc_pilot_imr": pd.read_csv(cfg.TAB_DIR / "C01_imr_pilot_oee.csv"), "improvement_scenario": scen}.items():
        df.to_csv(cfg.BI_DIR / f"{n}.csv", index=False)

    with open(cfg.OUT_DIR / "key_metrics.json", "w") as f:
        json.dump(km, f, indent=2, default=lambda o: float(o) if isinstance(o, (np.floating, np.integer)) else str(o))
    print("Pipeline complete ->", cfg.OUT_DIR)


if __name__ == "__main__":
    main()
