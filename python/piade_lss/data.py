"""Load, validate and enrich PIADE data (Measure phase: data collection + MSA-style integrity checks)."""
from __future__ import annotations
import numpy as np
import pandas as pd
from . import config as C


def load_raw(path=None) -> pd.DataFrame:
    path = path or C.DATA_DIR / "raw_data.csv"
    df = pd.read_csv(path)
    df["ts"] = pd.to_datetime(df["start"], unit="s", utc=True)
    df["ts_end"] = pd.to_datetime(df["end"], unit="s", utc=True)
    df["elapsed_s"] = df["elapsed"] / 1000.0            # elapsed is in milliseconds
    return df.sort_values(["equipment_ID", "start"]).reset_index(drop=True)


def integrity_report(df: pd.DataFrame) -> pd.DataFrame:
    """Data-integrity checks used in place of a Gage R&R (sensor logs can't be re-measured)."""
    g = df.groupby("equipment_ID")
    gap = g["start"].shift(-1) - df["end"]
    dpi = df["pi"] - g["pi"].shift(1)
    dpo = df["po"] - g["po"].shift(1)
    checks = {
        "rows": len(df),
        "duplicate rows": int(df.duplicated().sum()),
        "null cells": int(df.isna().sum().sum()),
        "elapsed vs (end-start) mismatch > 1%": int((abs(df["elapsed_s"] - (df["end"] - df["start"])) > 0.01 * df["elapsed_s"] + 0.01).sum()),
        "overlapping intervals (gap < -1 s)": int((gap < -1).sum()),
        "logging gaps > 1 h": int((gap > 3600).sum()),
        "negative counter deltas (pi)": int((dpi < 0).sum()),
        "negative counter deltas (po)": int((dpo < 0).sum()),
        "alarm on non-downtime row": int(((df["alarm"] != "A_000") & (df["type"] != "downtime")).sum()),
        "downtime row without alarm": int(((df["alarm"] == "A_000") & (df["type"] == "downtime")).sum()),
    }
    return pd.DataFrame({"check": list(checks), "result": list(checks.values())})


def enrich(df: pd.DataFrame) -> pd.DataFrame:
    """Per-interval counts (deltas of cumulative counters) + ideal output."""
    df = df.copy()
    g = df.groupby("equipment_ID")
    df["d_in"] = df["pi"] - g["pi"].shift(1)
    df["d_out"] = df["po"] - g["po"].shift(1)
    df["ideal_units"] = df["speed"] * df["elapsed_s"] / 3600.0
    glitch = (df["d_in"] < 0) | (df["d_out"] < 0) | (df["d_in"] > C.COUNTER_GLITCH_FACTOR * df["ideal_units"] + C.COUNTER_GLITCH_SLACK)
    df["counter_valid"] = ~glitch & df["d_in"].notna()
    df.loc[~df["counter_valid"], ["d_in", "d_out"]] = np.nan
    df["is_run"] = df["type"].isin(["production", "performance_loss"])
    df["ideal_run_units"] = np.where(df["is_run"], df["ideal_units"], 0.0)
    df["state_change"] = (df["type"] != g["type"].shift(1)).astype(int)
    df["hour"] = df["ts"].dt.hour
    df["shift"] = df["hour"].map({h: s for s, hs in C.SHIFTS.items() for h in hs})
    return df


def split_by_day(df: pd.DataFrame) -> pd.DataFrame:
    """Split intervals that cross midnight so daily time buckets are exact."""
    day0 = df["ts"].dt.floor("D")
    day1 = (df["ts_end"] - pd.Timedelta(microseconds=1)).dt.floor("D")
    simple = df[day0 == day1].assign(date=day0[day0 == day1], frac=1.0)
    cross = df[day0 != day1]
    parts = []
    for _, r in cross.iterrows():
        d, total = r["ts"].floor("D"), max(r["elapsed_s"], 1e-9)
        cur = r["ts"]
        while cur < r["ts_end"]:
            nxt = min(d + pd.Timedelta(days=1), r["ts_end"])
            rr = r.copy(); rr["date"] = d; rr["frac"] = (nxt - cur).total_seconds() / total
            parts.append(rr); cur, d = nxt, d + pd.Timedelta(days=1)
    out = pd.concat([simple, pd.DataFrame(parts)], ignore_index=True) if parts else simple
    for c in ["elapsed_s", "d_in", "d_out", "ideal_units", "ideal_run_units"]:
        out[c] = out[c] * out["frac"]
    out["date"] = pd.to_datetime(out["date"]).dt.tz_localize(None)
    return out


def daily_machine(df: pd.DataFrame) -> pd.DataFrame:
    """Daily OEE building blocks per machine."""
    s = split_by_day(df)
    t = s.pivot_table(index=["equipment_ID", "date"], columns="type", values="elapsed_s", aggfunc="sum", fill_value=0)
    t = t.reindex(columns=C.STATES, fill_value=0).add_suffix("_s")
    agg = s.groupby(["equipment_ID", "date"]).agg(
        units_in=("d_in", "sum"), units_out=("d_out", "sum"), ideal_run_units=("ideal_run_units", "sum"),
        stop_events=("type", lambda x: int((x == "downtime").sum())), state_changes=("state_change", "sum"))
    d = t.join(agg).reset_index()
    d["logged_s"] = d[[f"{x}_s" for x in C.STATES]].sum(axis=1)
    return add_oee(d)


def add_oee(d: pd.DataFrame) -> pd.DataFrame:
    """OEE = Availability x Performance x Quality (TPM definition; idle counted as availability loss)."""
    d = d.copy()
    d["planned_s"] = d["logged_s"] - d["scheduled_downtime_s"]
    d["run_s"] = d["production_s"] + d["performance_loss_s"]
    d["availability"] = np.where(d["planned_s"] > 0, d["run_s"] / d["planned_s"], np.nan)
    d["performance"] = np.where(d["ideal_run_units"] > 0, np.minimum(d["units_in"] / d["ideal_run_units"], 1.0), np.nan)
    d["quality"] = np.where(d["units_in"] > 0, np.clip(d["units_out"] / d["units_in"], 0, 1), np.nan)
    d["oee"] = d["availability"] * d["performance"] * d["quality"]
    d["rejects"] = (d["units_in"] - d["units_out"]).clip(lower=0)
    return d


def downtime_events(df: pd.DataFrame) -> pd.DataFrame:
    """Merge consecutive downtime rows with the same alarm into one stop event; tag the preceding state."""
    x = df.copy()
    g = x.groupby("equipment_ID")
    x["prev_type"] = g["type"].shift(1)
    new = (x["type"] != g["type"].shift(1)) | (x["alarm"] != g["alarm"].shift(1))
    x["event_id"] = new.cumsum()
    ev = x[x["type"] == "downtime"].groupby("event_id").agg(
        equipment_ID=("equipment_ID", "first"), alarm=("alarm", "first"), ts=("ts", "first"),
        duration_s=("elapsed_s", "sum"), prev_type=("prev_type", "first"), shift=("shift", "first"))
    return ev.reset_index(drop=True)


def load_sequences(path=None) -> pd.DataFrame:
    path = path or C.DATA_DIR / "sequences_1h_data.csv"
    s = pd.read_csv(path).copy()
    s = s.copy()
    s["ts"] = pd.to_datetime(s["interval_start"], utc=True)
    return s
