"""Lean toolkit quantification: SMED baseline, Improve-phase OEE scenario (lever bridge),
VSM data boxes, COPQ. All reduction percentages are ASSUMED targets, not measured results."""
from __future__ import annotations
import numpy as np
import pandas as pd
from . import config as cfg
from .analysis import oee_summary

# Improve-phase levers: (name, loss bucket, alarms or None, assumed reduction, Lean tool)
LEVERS = [
    ("Poka-Yoke + autonomous maintenance on high-RPN modes", "downtime", ["A_001", "A_006"], 0.40, "Poka-Yoke / FMEA / TPM", "Poka-Yoke\n(A_001, A_006)"),
    ("Kaizen blitz on high-frequency micro-stops", "downtime", ["A_065", "A_101", "A_066"], 0.30, "Kaizen / 5 Whys", "Kaizen\n(A_065, A_101,\nA_066)"),
    ("5S + visual management on remaining alarms", "downtime", "other", 0.10, "5S / visual mgmt", "5S + visual\n(other alarms)"),
    ("Idle recovery: reason codes + Kanban supply + shift/night standard work", "idle", None, 0.25, "Kanban / Standard work / Poka-Yoke (data)", "Idle recovery\n(reason codes,\nKanban, staffing)"),
    ("CIL routine + speed standardisation", "speed", None, 0.20, "5S / TPM / Kaizen", "CIL + speed\nstandard"),
]


def smed_baseline(enriched: pd.DataFrame) -> pd.DataFrame:
    sd = enriched[(enriched["type"] == "scheduled_downtime") & enriched["elapsed_s"].between(cfg.CHANGEOVER_MIN_S, cfg.CHANGEOVER_MAX_S)]
    years = (enriched["ts"].max() - enriched["ts"].min()).days / 365
    t = sd.groupby("equipment_ID")["elapsed_s"].agg(events="size", mean_min=lambda x: x.mean() / 60,
                                                     median_min=lambda x: x.median() / 60, p90_min=lambda x: x.quantile(0.9) / 60,
                                                     hours="sum")
    t["hours"] /= 3600
    span = enriched.groupby("equipment_ID")["ts"].agg(lambda x: (x.max() - x.min()).days / 365)
    t["events_per_year"] = t["events"] / span
    t["hours_per_year"] = t["hours"] / span
    t["target_mean_min (-40%)"] = t["mean_min"] * 0.6
    t["hours_released_per_year"] = t["hours_per_year"] * 0.4
    return t.reset_index()


def improvement_scenario(daily: pd.DataFrame, events: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """OEE bridge: each lever converts lost hours back into run time at the current performance rate."""
    s = oee_summary(daily, by=None).iloc[0]
    ppt = s.planned_s / 3600
    run, P, Q = s.run_s / 3600, s.performance, s.quality
    alarm_h = events.groupby("alarm")["duration_s"].sum() / 3600
    named = [a for lv in LEVERS if isinstance(lv[2], list) for a in lv[2]]
    rows, oee0 = [], run * P * Q / ppt
    cur_run, cur_P = run, P
    rows.append({"step": "Baseline", "label": "Baseline", "tool": "", "assumed_reduction": 0.0, "hours_recovered": 0.0, "oee": oee0})
    for name, bucket, alarms, red, tool, label in LEVERS:
        if bucket == "downtime":
            base_h = alarm_h.reindex(alarms, fill_value=0).sum() if isinstance(alarms, list) else alarm_h.drop(named, errors="ignore").sum()
            gain = base_h * red; cur_run += gain
        elif bucket == "idle":
            gain = s.idle_s / 3600 * red; cur_run += gain
        else:  # speed loss: close part of the gap between actual and rated output
            gain = cur_run * (1 - cur_P) * red
            cur_P = cur_P + (1 - cur_P) * red
        rows.append({"step": name, "label": label, "tool": tool, "assumed_reduction": red, "hours_recovered": gain, "oee": cur_run * cur_P * Q / ppt})
    t = pd.DataFrame(rows)
    t["delta_pts"] = t["oee"].diff().fillna(0) * 100
    years = (daily["date"].max() - daily["date"].min()).days / 365
    ideal_rate = s.ideal_run_units / (s.run_s / 3600)                      # packs per run-hour at rated speed
    extra_packs_yr = (t["oee"].iloc[-1] - oee0) * ppt * ideal_rate / years
    fin = {"baseline_oee": oee0, "projected_oee": t["oee"].iloc[-1], "planned_hours_per_year": ppt / years,
           "extra_good_packs_per_year": extra_packs_yr,
           "contribution_gain_INR_per_year": extra_packs_yr * cfg.CONTRIBUTION_PER_PACK_INR,
           "copq_rejects_INR_per_year": s.rejects / years * cfg.CONTRIBUTION_PER_PACK_INR,
           "lost_packs_vs_ideal_per_year": (1 - oee0) * ppt * ideal_rate / years}
    return t, fin


def vsm_data(daily: pd.DataFrame, events: pd.DataFrame, smed: pd.DataFrame, pol: pd.DataFrame, machine="s_1") -> dict:
    s = oee_summary(daily).loc[machine]
    ev = events[events["equipment_ID"] == machine]
    sp = daily[daily["equipment_ID"] == machine]
    rated = s.ideal_run_units / (s.run_s / 3600)
    p = pol[(pol["equipment_ID"] == machine) & np.isclose(pol["service_level"], cfg.TARGET_SERVICE_LEVEL)].iloc[0]
    sm = smed.set_index("equipment_ID").loc[machine]
    return {"machine": machine, "cycle_time_s": 3600 / rated, "rated_packs_per_h": rated,
            "availability": s.availability, "performance": s.performance, "quality": s.quality, "oee": s.oee,
            "uptime_run_over_logged": s.utilization, "changeover_mean_min": sm["mean_min"],
            "changeovers_per_year": sm["events_per_year"], "stops_per_run_hour": len(ev) / (s.run_s / 3600),
            "mttr_min": ev["duration_s"].mean() / 60, "avg_daily_demand": p["mean_daily"],
            "rm_days_cover_policy": p["days_of_cover_avg"], "safety_stock": p["safety_stock"], "rop": p["reorder_point"], "eoq": p["EOQ"]}
