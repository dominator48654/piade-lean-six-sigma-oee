"""All project figures (matplotlib). Every function saves one PNG into outputs/figures."""
from __future__ import annotations
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Polygon, FancyArrowPatch
from . import config as cfg

NAVY, TEAL, AMBER, ORANGE, RED, GREY, LIGHT = "#1F3A5F", "#2A9D8F", "#E9C46A", "#F4A261", "#E76F51", "#8D99AE", "#EEF2F6"
PAL = {"s_1": NAVY, "s_2": RED, "s_3": TEAL, "s_4": ORANGE, "s_5": "#6D597A"}
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9.5, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.titleweight": "bold", "axes.titlesize": 11, "figure.dpi": 110, "savefig.dpi": 160,
                     "savefig.bbox": "tight", "axes.grid": True, "grid.alpha": 0.25})


def _save(fig, name):
    cfg.FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(cfg.FIG_DIR / f"{name}.png")
    plt.close(fig)


# ------------------------------------------------------------------ Measure
def oee_by_machine(summ: pd.DataFrame, fleet: pd.Series):
    t = pd.concat([summ, fleet.to_frame("Fleet").T])
    fig, ax = plt.subplots(figsize=(9, 4.2))
    x = np.arange(len(t)); w = 0.2
    for i, (c, col, lab) in enumerate([("availability", TEAL, "Availability"), ("performance", AMBER, "Performance"),
                                       ("quality", GREY, "Quality"), ("oee", NAVY, "OEE")]):
        b = ax.bar(x + (i - 1.5) * w, t[c], w, color=col, label=lab)
        if c == "oee":
            ax.bar_label(b, labels=[f"{v:.0%}" for v in t[c]], fontsize=8, padding=2, fontweight="bold")
    ax.axhline(cfg.OEE_TARGET, color=RED, ls="--", lw=1.2, label=f"OEE target {cfg.OEE_TARGET:.0%}")
    ax.set_xticks(x, t.index); ax.set_ylim(0, 1.1); ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1))
    ax.set_title("Baseline OEE = Availability x Performance x Quality (Jan 2020 - Dec 2021)")
    ax.legend(ncol=5, loc="upper left", frameon=False, fontsize=8)
    _save(fig, "M01_oee_by_machine")


def loss_waterfall(tree: pd.DataFrame):
    h = tree.set_index("node")["hours"]
    steps = [("Planned\nproduction time", h["2"], "total"), ("Alarm\ndowntime", -h["2.1"], "loss"), ("Idle\n(no reason code)", -h["2.2"], "loss"),
             ("Reduced speed /\nminor stops", -h["3.1"], "loss"), ("Sub-rated\nrunning", -h["3.2"], "loss"),
             ("Quality\nrejects", -h["4.1"], "loss"), ("Fully\nproductive time", h["5"], "total")]
    fig, ax = plt.subplots(figsize=(10, 4.4))
    cum = 0
    for i, (lab, v, kind) in enumerate(steps):
        if kind == "total":
            ax.bar(i, v, color=NAVY if i == 0 else TEAL); cum = v; top = v
        else:
            ax.bar(i, v, bottom=cum, color=RED if abs(v) > 3000 else ORANGE); top = cum; cum += v
        ax.text(i, top + 400, f"{abs(v):,.0f} h\n{abs(v)/h['2']:.1%}", ha="center", fontsize=8)
    ax.set_xticks(range(len(steps)), [s[0] for s in steps], fontsize=8.5)
    ax.set_ylabel("Machine-hours (5 machines, 2 years)"); ax.set_ylim(0, h["2"] * 1.15)
    ax.set_title("OEE loss waterfall: where planned time goes")
    _save(fig, "M02_loss_waterfall")


def loss_tree_diagram(tree: pd.DataFrame):
    t = tree.set_index("node")
    logged = t.loc["0", "hours"]
    short = {"0": "Logged time", "1": "Scheduled downtime", "1.1": "Changeover / cleaning (10 min-4 h)", "1.2": "Long shutdowns (> 4 h)",
             "1.3": "Short planned stops (< 10 min)", "2": "Planned production time (PPT)", "2.1": "Alarm downtime (availability)",
             "2.2": "Idle, no reason code (availability)", "3": "Run time", "3.1": "Reduced speed / minor stops", "3.2": "Sub-rated running",
             "4": "Net run time", "4.1": "Quality rejects", "5": "Fully productive time = OEE"}
    fig, ax = plt.subplots(figsize=(15, 8)); ax.axis("off"); ax.set_xlim(0, 15); ax.set_ylim(0, 8.2); ax.grid(False)
    W, Hh = 2.6, 0.6
    def box(x, y, node, col=LIGHT, ec=NAVY, w=W, h=Hh):
        r = t.loc[node]
        name = short.get(node, r["name"])
        pct = f"{r['hours']/logged:.1%} of logged" if node in ("0", "1", "1.1", "1.2", "1.3") else f"{r['pct_of_planned']:.1%} of PPT"
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.06", fc=col, ec=ec, lw=1.1))
        ax.text(x + w / 2, y + h * 0.66, name, ha="center", va="center", fontsize=7.6)
        ax.text(x + w / 2, y + h * 0.27, f"{r['hours']:,.0f} h | {pct}", ha="center", va="center", fontsize=7.3, fontweight="bold", color=NAVY)
        return (x, y, w, h)
    def link(a, b):
        x0, y0 = a[0] + a[2], a[1] + a[3] / 2
        x1, y1 = b[0], b[1] + b[3] / 2
        xm = x0 + 0.18
        ax.plot([x0, xm, xm, x1], [y0, y0, y1, y1], color=GREY, lw=0.9)
    grey, red, org, blue, green = ("#F3F3F3", GREY), ("#FBE3DC", RED), ("#FFF4EC", ORANGE), ("#DDE6F0", NAVY), ("#D8F0EC", TEAL)
    b0 = box(0.1, 3.9, "0", *blue)
    b1 = box(3.0, 6.9, "1", *grey); b2 = box(3.0, 3.9, "2", *blue)
    b11 = box(6.0, 7.5, "1.1", *grey); b12 = box(6.0, 6.8, "1.2", *grey); b13 = box(6.0, 6.1, "1.3", *grey)
    b21 = box(6.0, 5.0, "2.1", *red); b22 = box(6.0, 4.2, "2.2", *red); b3 = box(6.0, 2.4, "3", *blue)
    kids, y = [], 5.75
    for n in [n for n in t.index if n.startswith("2.1.")]:
        kids.append(box(9.0, y, n, *org, h=0.5)); y -= 0.58
    b31 = box(9.0, 1.95, "3.1", *org); b32 = box(9.0, 1.25, "3.2", *org); b4 = box(9.0, 0.4, "4", *blue)
    b41 = box(12.1, 0.95, "4.1", *org); b5 = box(12.1, 0.15, "5", *green)
    for a, b in [(b0, b1), (b0, b2), (b1, b11), (b1, b12), (b1, b13), (b2, b21), (b2, b22), (b2, b3), (b3, b31), (b3, b32), (b3, b4), (b4, b41), (b4, b5)] + [(b21, k) for k in kids]:
        link(a, b)
    ax.text(12.1, 7.6, "Reading the tree", fontsize=9, fontweight="bold", color=NAVY)
    ax.text(12.1, 7.45, "Grey = planned (excluded from OEE)\nRed = availability losses\nOrange = alarm / speed / quality detail\nGreen = value-adding time", fontsize=7.8, va="top")
    ax.set_title("Downtime / OEE loss tree - fleet of 5 packaging machines, Jan 2020 - Dec 2021", loc="left")
    _save(fig, "M03_loss_tree")


def pareto_chart(p: pd.DataFrame, metric: str, name: str, title: str, top=15):
    q = p.head(top)
    fig, ax = plt.subplots(figsize=(10, 4.3))
    cols = [RED if c.startswith("A (") else (AMBER if c == "B" else GREY) for c in q["class"]]
    ax.bar(q["alarm"], q[metric], color=cols)
    ax.set_ylabel("Downtime hours" if metric == "hours" else "Number of stops")
    ax2 = ax.twinx(); ax2.plot(q["alarm"], q["cum_share"] * 100, "o-", color=NAVY, ms=4); ax2.axhline(80, color=NAVY, ls=":", lw=1)
    ax2.set_ylim(0, 105); ax2.set_ylabel("Cumulative %"); ax2.grid(False); ax2.spines["right"].set_visible(True)
    ax.tick_params(axis="x", rotation=45); ax.set_title(title)
    n80 = int((p["cum_share"] < 0.8).sum() + 1)
    ax.text(0.99, 0.95, f"{n80} of {len(p)} alarm codes -> 80% of {'downtime' if metric=='hours' else 'stops'}", transform=ax.transAxes, ha="right", fontsize=9, color=RED, fontweight="bold")
    _save(fig, name)


def alarm_machine_heatmap(events: pd.DataFrame, top_alarms):
    x = events[events["alarm"].isin(top_alarms)].pivot_table(index="alarm", columns="equipment_ID", values="duration_s", aggfunc="sum", fill_value=0) / 3600
    x = x.loc[top_alarms]
    fig, ax = plt.subplots(figsize=(6.5, 5))
    im = ax.imshow(x.values, cmap="OrRd", aspect="auto")
    ax.set_xticks(range(x.shape[1]), x.columns); ax.set_yticks(range(x.shape[0]), x.index); ax.grid(False)
    for i in range(x.shape[0]):
        for j in range(x.shape[1]):
            v = x.values[i, j]
            ax.text(j, i, f"{v:,.0f}" if v else "-", ha="center", va="center", fontsize=8, color="white" if v > x.values.max() * 0.5 else "black")
    fig.colorbar(im, ax=ax, label="Downtime hours"); ax.set_title("Stratification: top alarms x machine (hours)")
    _save(fig, "M06_alarm_machine_heatmap")


def time_heatmaps(enriched: pd.DataFrame):
    e = enriched.assign(wd=enriched["ts"].dt.dayofweek)
    fig, axes = plt.subplots(1, 2, figsize=(12, 3.6))
    for ax, st, cmap in [(axes[0], "idle", "Blues"), (axes[1], "downtime", "Reds")]:
        x = e.groupby(["wd", "hour", "type"])["elapsed_s"].sum().unstack(fill_value=0)
        share = (x[st] / x.sum(axis=1)).unstack()
        im = ax.imshow(share.values, aspect="auto", cmap=cmap); ax.grid(False)
        ax.set_yticks(range(7), ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]); ax.set_xticks(range(0, 24, 2), range(0, 24, 2))
        ax.set_xlabel("Hour of day (UTC)"); ax.set_title(f"{st.capitalize()} share of logged time")
        fig.colorbar(im, ax=ax, format=matplotlib.ticker.PercentFormatter(1))
    _save(fig, "M07_time_heatmaps")


def monthly_trend(daily: pd.DataFrame):
    d = daily.assign(m=daily["date"].dt.to_period("M").dt.to_timestamp())
    fig, ax = plt.subplots(figsize=(10, 4))
    def oee(g): return g["run_s"].sum() / g["planned_s"].sum() * g["units_out"].sum() / g["ideal_run_units"].sum()
    for m, g in d.groupby("equipment_ID"):
        s = g.groupby("m").apply(oee); ax.plot(s.index, s.values, color=PAL[m], lw=1, alpha=0.7, label=m)
    f = d.groupby("m").apply(oee); ax.plot(f.index, f.values, color="black", lw=2.5, label="Fleet")
    ax.axhline(cfg.OEE_TARGET, color=RED, ls="--", lw=1); ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1))
    ax.set_title("Run chart: monthly OEE by machine"); ax.legend(ncol=6, frameon=False, fontsize=8, loc="lower left")
    _save(fig, "M08_monthly_oee_run_chart")


def reliability_chart(rel: pd.DataFrame):
    fig, ax = plt.subplots(1, 2, figsize=(10, 3.5))
    ax[0].bar(rel.index, rel["MTBF_min"], color=TEAL); ax[0].set_title("MTBF (run-minutes between alarm stops)")
    ax[1].bar(rel.index, rel["MTTR_min"], color=RED); ax[1].set_title("MTTR (minutes per alarm stop)")
    for a, c in zip(ax, ["MTBF_min", "MTTR_min"]):
        a.bar_label(a.containers[0], labels=[f"{v:.1f}" for v in rel[c]], fontsize=8)
    _save(fig, "M09_mtbf_mttr")


# ------------------------------------------------------------------ Analyze
def fishbone():
    import textwrap
    fig, ax = plt.subplots(figsize=(17, 8)); ax.axis("off"); ax.set_xlim(0, 19); ax.set_ylim(0, 8); ax.grid(False)
    ax.annotate("", xy=(15.6, 4), xytext=(0.3, 4), arrowprops=dict(arrowstyle="-|>", lw=2.5, color=NAVY))
    ax.add_patch(FancyBboxPatch((15.7, 3.05), 3.1, 1.9, boxstyle="round,pad=0.05", fc=NAVY, ec=NAVY))
    ax.text(17.25, 4, "EFFECT\nFleet OEE 51.7%\nvs 65% target\n(pilot s_1 fell\n4.5 pts in 2021)", ha="center", va="center", color="white", fontsize=9.5, fontweight="bold")
    cats = {
        "MACHINE": (4.6, True, ["A_065 micro-stops on s_1: 858 h, 18.9k stops [data]", "A_101 repeat stops on s_2/s_3/s_5: 515 h [data]",
                                  "A_001 / A_006: longest stops, MTTR 5-6 min [data]", "s_4 spends 21% of time in reduced-speed state [data]"]),
        "METHOD": (9.6, True, ["Changeovers average 37-68 min; no standard [data]", "Shift A alarm-downtime share 9.8% vs 7.5-7.6% [data]",
                                 "No start-up / restart checklist [hyp.]", "Clean-Inspect-Lube not routinised [hyp.]"]),
        "MEASUREMENT": (14.6, True, ["Idle state has NO reason code (27% of PPT) [data]", "Alarm codes anonymised, no hierarchy [data]",
                                      "85 counter resets / glitches [data]", "OEE not reviewed daily at the line [hyp.]"]),
        "PEOPLE": (4.6, False, ["Night shift (C) idle 38.5% vs 27.0% (A), 19.4% (B) [data]", "Weekend idle 35.9% vs 26.7% on weekdays [data]",
                                  "Shift-handover gaps [hyp.]", "Skill variance in stop recovery [hyp.]"]),
        "MATERIAL": (9.6, False, ["Line starvation hidden inside idle time [hyp.]", "Blank / film variation drives jams [hyp.]",
                                    "No line-side replenishment signal [hyp.]"]),
        "ENVIRONMENT": (14.6, False, ["s_1 OEE fell 66.7% -> 62.2% in 2021; other 4 machines rose [data]", "Volume on s_2 and s_4 up ~2.7x in 2021 [data]",
                                       "Seasonal demand swings [hyp.]"]),
    }
    for name, (x, top, causes) in cats.items():
        y1 = 7.3 if top else 0.7
        ax.plot([x, x - 1.9], [4, y1], color=NAVY, lw=1.8)
        ax.text(x - 1.9, y1 + (0.25 if top else -0.35), name, ha="center", fontsize=11, fontweight="bold", color=RED)
        for i, c in enumerate(causes):
            frac = (i + 0.7) / (len(causes) + 0.4)
            yy = y1 + (4 - y1) * frac
            xx = (x - 1.9) + 1.9 * frac
            ax.plot([xx - 0.25, xx], [yy, yy], color=GREY, lw=0.8)
            data = "[data]" in c
            ax.text(xx - 0.3, yy, textwrap.fill(c, 30), ha="right", va="center", fontsize=7.4, color=NAVY if data else "#666666",
                    fontweight="bold" if data else "normal", linespacing=1.05)
    ax.set_title("Cause & effect (Ishikawa, 6M).  Bold [data] = verified in the PIADE data;  grey [hyp.] = hypothesis to verify at the gemba", loc="left")
    _save(fig, "A01_fishbone")


def hypothesis_plots(daily: pd.DataFrame, enriched: pd.DataFrame):
    fig, ax = plt.subplots(1, 2, figsize=(11, 3.8))
    d = daily.dropna(subset=["oee"])
    data = [g["oee"].values for _, g in d.groupby("equipment_ID")]
    bp = ax[0].boxplot(data, patch_artist=True, showfliers=False); ax[0].set_xticks(range(1, 6), sorted(d["equipment_ID"].unique()))
    for patch, m in zip(bp["boxes"], sorted(d["equipment_ID"].unique())): patch.set_facecolor(PAL[m]); patch.set_alpha(0.6)
    ax[0].yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1)); ax[0].set_title("Daily OEE by machine (Kruskal-Wallis p<0.001)")
    sh = enriched.groupby(["equipment_ID", enriched["ts"].dt.date, "shift", "type"])["elapsed_s"].sum().unstack(fill_value=0)
    sh = sh.div(sh.sum(axis=1), axis=0).reset_index()
    order = sorted(sh["shift"].unique())
    bp = ax[1].boxplot([sh[sh["shift"] == s]["idle"] for s in order], patch_artist=True, showfliers=False)
    for p_, c in zip(bp["boxes"], [TEAL, AMBER, NAVY]): p_.set_facecolor(c); p_.set_alpha(0.6)
    ax[1].set_xticks(range(1, 4), order); ax[1].yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1))
    for i, s in enumerate(order, 1): ax[1].text(i, sh[sh["shift"] == s]["idle"].mean(), f"mean {sh[sh['shift']==s]['idle'].mean():.1%}", ha="center", fontsize=8, color=RED, fontweight="bold")
    ax[1].set_title("Idle share by shift (Kruskal-Wallis p<0.001)")
    _save(fig, "A02_hypothesis_boxplots")


def regression_plot(coef: pd.DataFrame, info: dict):
    c = coef[(coef["model"] == "M1") & coef["minutes_per_stop"].notna()].sort_values("minutes_per_stop")
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.barh(c["term"], c["minutes_per_stop"], xerr=[(c["coef"] - c["ci_low"]) * 60, (c["ci_high"] - c["coef"]) * 60], color=ORANGE, ecolor=NAVY, capsize=3)
    ax.set_xlabel("Incremental downtime minutes per stop (OLS coef x 60, 95% CI)")
    ax.set_title(f"Regression M1: hourly downtime share ~ alarm stop counts (R2={info['M1']['r2']:.2f}, n={info['M1']['n']:,})", fontsize=10)
    _save(fig, "A03_regression_minutes_per_stop")


def fmea_bubble(f: pd.DataFrame):
    fig, ax = plt.subplots(figsize=(8, 4.8))
    col = f["action_priority"].map({"High": RED, "Medium": ORANGE, "Low": GREY})
    ax.scatter(f["downtime_h"], f["RPN"], s=f["stops"] / 40 + 30, c=col, alpha=0.75, edgecolor="k")
    for _, r in f.iterrows(): ax.annotate(r["failure_mode"], (r["downtime_h"], r["RPN"]), xytext=(5, 4), textcoords="offset points", fontsize=8)
    ax.set_xlabel("Downtime hours (Pareto impact)"); ax.set_ylabel("RPN = S x O x D (risk)")
    ax.set_title("Pareto vs FMEA: impact is not the same as risk (bubble = stop count)")
    _save(fig, "A04_fmea_vs_pareto")


def smed_plot(enriched: pd.DataFrame):
    sd = enriched[(enriched["type"] == "scheduled_downtime") & enriched["elapsed_s"].between(cfg.CHANGEOVER_MIN_S, cfg.CHANGEOVER_MAX_S)]
    ms = sorted(sd["equipment_ID"].unique())
    fig, ax = plt.subplots(figsize=(8, 3.8))
    bp = ax.boxplot([sd[sd["equipment_ID"] == m]["elapsed_s"] / 60 for m in ms], patch_artist=True, showfliers=False)
    for p_, m in zip(bp["boxes"], ms): p_.set_facecolor(PAL[m]); p_.set_alpha(0.6)
    ax.set_xticks(range(1, 6), ms); ax.set_ylabel("Minutes per changeover-like stop")
    ax.set_title("SMED baseline: planned stops of 10 min - 4 h (changeover / cleaning proxy)")
    _save(fig, "I02_smed_baseline")


# ------------------------------------------------------------------ Improve
def improvement_bridge(t: pd.DataFrame):
    fig, ax = plt.subplots(figsize=(10.5, 4.3))
    base = t["oee"].iloc[0]
    ax.bar(0, base, color=NAVY); ax.text(0, base + 0.005, f"{base:.1%}", ha="center", fontweight="bold")
    cum = base
    for i, r in enumerate(t.iloc[1:].itertuples(), 1):
        d = r.oee - cum; ax.bar(i, d, bottom=cum, color=TEAL); ax.text(i, r.oee + 0.005, f"+{d*100:.1f} pts", ha="center", fontsize=8.5)
        cum = r.oee
    n = len(t); ax.bar(n, cum, color=TEAL, edgecolor=NAVY); ax.text(n, cum + 0.005, f"{cum:.1%}", ha="center", fontweight="bold")
    labels = list(t["label"]) + ["Projected"]
    ax.set_xticks(range(n + 1), labels, fontsize=8); ax.set_ylim(0.4, 0.7)
    ax.axhline(cfg.OEE_TARGET, color=RED, ls="--", lw=1); ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1))
    ax.set_title("Improve: projected OEE bridge by Lean lever (ASSUMED reduction rates - to be validated in pilot)")
    _save(fig, "I01_oee_improvement_bridge")


def vsm(v: dict, future=False):
    fig, ax = plt.subplots(figsize=(14, 7.5)); ax.axis("off"); ax.set_xlim(0, 14); ax.set_ylim(0, 7.5); ax.grid(False)
    def proc(x, y, title, lines, w=2.2, col=LIGHT):
        ax.add_patch(FancyBboxPatch((x, y), w, 0.7, boxstyle="square,pad=0", fc=NAVY, ec=NAVY))
        ax.text(x + w / 2, y + 0.35, title, ha="center", va="center", color="white", fontweight="bold", fontsize=8.5)
        ax.add_patch(FancyBboxPatch((x, y - 0.25 * len(lines) - 0.1), w, 0.25 * len(lines) + 0.1, boxstyle="square,pad=0", fc=col, ec=NAVY))
        for i, l in enumerate(lines): ax.text(x + 0.08, y - 0.2 - 0.25 * i, l, fontsize=7.3, va="center")
    def factory(x, y, label):
        ax.add_patch(Polygon([[x, y], [x, y + 0.6], [x + 0.4, y + 0.9], [x + 0.4, y + 0.6], [x + 0.8, y + 0.9], [x + 0.8, y + 0.6], [x + 1.2, y + 0.9], [x + 1.2, y]], fc=LIGHT, ec=NAVY))
        ax.text(x + 0.6, y + 0.25, label, ha="center", fontsize=8, fontweight="bold")
    def tri(x, y, txt):
        ax.add_patch(Polygon([[x, y], [x + 0.5, y], [x + 0.25, y + 0.45]], fc=AMBER, ec="k")); ax.text(x + 0.25, y + 0.12, "I", ha="center", fontsize=8, fontweight="bold")
        ax.text(x + 0.25, y - 0.22, txt, ha="center", fontsize=7.3, va="top")
    def arrow(a, b, style="-|>", col="k", ls="-"):
        ax.add_patch(FancyArrowPatch(a, b, arrowstyle=style, mutation_scale=12, color=col, ls=ls, lw=1.2))
    def burst(x, y, txt):
        ax.add_patch(Polygon([[x + 1.05 * np.cos(t) * (1 if i % 2 else 0.78), y + 0.55 * np.sin(t) * (1 if i % 2 else 0.78)] for i, t in enumerate(np.linspace(0, 2 * np.pi, 25)[:-1])], fc="#FFE066", ec=RED))
        ax.text(x, y, txt, ha="center", va="center", fontsize=6.8, fontweight="bold", color=RED)
    factory(0.3, 6.1, "Film / carton\nsupplier"); factory(12.4, 6.1, "Customer /\nDC")
    ax.add_patch(FancyBboxPatch((5.4, 6.2), 3.2, 0.8, boxstyle="square,pad=0", fc=LIGHT, ec=NAVY))
    ax.text(7.0, 6.6, "Production control (MRP / S&OP)" + ("\n+ Power BI OEE & inventory cockpit" if future else ""), ha="center", va="center", fontsize=8, fontweight="bold")
    arrow((5.4, 6.55), (1.6, 6.55), col=NAVY, ls="--"); ax.text(3.5, 6.7, ("ROP-triggered orders: EOQ %s blanks" % f"{v['eoq']:,.0f}") if future else "Monthly bulk PO (current practice, ASSUMED)", ha="center", fontsize=7.3)
    arrow((12.4, 6.55), (8.6, 6.55), col=NAVY, ls="--"); ax.text(10.5, 6.7, "Daily orders / forecast", ha="center", fontsize=7.3)
    y = 3.6
    ax.add_patch(FancyArrowPatch((0.9, 6.05), (0.8, 4.2), arrowstyle="simple", mutation_scale=18, fc=GREY, ec=GREY))
    ax.text(1.05, 5.1, "Truck:\nweekly" if not future else "Truck:\non ROP trigger", fontsize=7.3)
    if future:
        tri(0.55, y, f"RM store\nSS {v['safety_stock']/1e3:,.0f}k + EOQ/2\n~{v['rm_days_cover_policy']:.1f} days avg cover")
    else:
        tri(0.55, y, "RM store\n~15 days cover\n(ASSUMED current)")
    arrow((1.2, y + 0.2), (2.0, y + 0.2), style="-|>")
    proc(2.0, y, "Line-side buffer", ["Kanban: 19 bins x 2,000" if future else "Push delivery by shift", "Replenish: 8 h loop" if future else "Starvation risk (idle 9%)"], w=2.0)
    arrow((4.0, y + 0.35), (5.0, y + 0.35))
    oee_f = v["oee"] if not future else v.get("oee_future", v["oee"])
    lines = [f"C/T: {v['cycle_time_s']:.2f} s/pack ({v['rated_packs_per_h']:,.0f}/h)",
             f"OEE: {v['oee']:.1%}" + (f" -> target {v.get('oee_future', 0):.1%}" if future else ""),
             f"A {v['availability']:.1%} | P {v['performance']:.1%} | Q {v['quality']:.1%}",
             f"C/O: {v['changeover_mean_min']:.0f} min" + (f" -> {v['changeover_mean_min']*0.6:.0f} min (SMED)" if future else f" x {v['changeovers_per_year']:.0f}/yr"),
             f"Alarm stops: {v['stops_per_run_hour']:.1f}/run-h, MTTR {v['mttr_min']:.1f} min",
             "Shifts: 3 x 8 h"]
    proc(5.0, y, f"Packaging machine {v['machine']}", lines, w=3.3, col="#FFFFFF")
    arrow((8.3, y + 0.35), (9.2, y + 0.35))
    tri(9.2, y, "FG store\n~3 days\n(ASSUMED)" if not future else "FG store\n~2 days\n(FIFO lanes)")
    arrow((9.8, y + 0.2), (12.9, 6.1))
    if future:
        burst(6.6, 5.2, "Kaizen:\nA_065\nmicro-stops"); burst(3.0, 5.2, "Kanban +\nidle reason\ncodes")
        burst(9.6, 5.2, "SMED\n-40%\nchangeover"); burst(10.3, 2.45, "Poka-Yoke\nA_001 / A_006\n+ CIL / 5S")
        ax.add_patch(FancyArrowPatch((3.2, y - 0.75), (1.0, y - 0.1), connectionstyle="arc3,rad=-0.4", arrowstyle="-|>", mutation_scale=12, color=TEAL, lw=1.5, ls="--"))
        ax.text(2.0, 2.35, "Kanban withdrawal loop", color=TEAL, fontsize=7.5, fontweight="bold")
    # lead-time ladder
    rm_days = v["rm_days_cover_policy"] if future else 15
    fg = 2 if future else 3
    ls_days = (19 * 2000 / v["avg_daily_demand"]) if future else 1.0
    pt_s = v["cycle_time_s"]
    ax.plot([0.4, 4.4, 4.4, 8.8, 8.8, 11.5], [0.95, 0.95, 0.5, 0.5, 0.95, 0.95], color="k", lw=1)
    ax.plot([2.0, 2.0], [0.88, 1.02], color="k", lw=1)
    ax.text(1.2, 1.05, f"RM {rm_days:.1f} d", ha="center", fontsize=8); ax.text(3.2, 1.05, f"Line-side {ls_days:.1f} d", ha="center", fontsize=8)
    ax.text(6.6, 0.3, f"Value-added: {pt_s:.2f} s per pack", ha="center", fontsize=8, fontweight="bold", color=TEAL)
    ax.text(10.15, 1.05, f"FG {fg} d", ha="center", fontsize=8)
    lt = rm_days + ls_days + fg
    ax.add_patch(FancyBboxPatch((11.9, 0.25), 1.9, 0.85, boxstyle="square,pad=0", fc=LIGHT, ec=NAVY))
    ax.text(12.85, 0.68, f"Lead time ~{lt:.1f} days\nVA time {pt_s:.2f} s / pack", ha="center", va="center", fontsize=8, fontweight="bold")
    ax.set_title(("FUTURE" if future else "CURRENT") + f"-state Value Stream Map - pilot machine {v['machine']} (packaging material -> packed goods)", loc="left")
    _save(fig, "I03_vsm_future" if future else "M10_vsm_current")


# ------------------------------------------------------------------ Control / SPC
def imr_chart(ch: dict, flags: pd.DataFrame, phase_split, title, name, pct=True):
    x = ch["x"]
    fig, ax = plt.subplots(2, 1, figsize=(11, 5.6), sharex=True, gridspec_kw={"height_ratios": [2.2, 1]})
    ax[0].plot(x.index, x.values, lw=0.8, color=NAVY, marker="o", ms=2)
    out = flags.any(axis=1)
    ax[0].scatter(x.index[flags["rule1"]], x[flags["rule1"]], color=RED, s=16, zorder=3, label="Rule 1 (beyond 3 sigma)")
    ax[0].scatter(x.index[out & ~flags["rule1"]], x[out & ~flags["rule1"]], color=ORANGE, s=10, zorder=3, label="Rules 2-4 (runs / trends)")
    for k, c, l in [("cl", TEAL, "-"), ("ucl", RED, "--"), ("lcl", RED, "--")]:
        ax[0].axhline(ch[k], color=c, ls=l, lw=1); ax[0].text(x.index[-1], ch[k], f" {k.upper()} {ch[k]:.1%}" if pct else f" {k.upper()} {ch[k]:.2f}", fontsize=7.5, va="center")
    ax[0].axvline(pd.Timestamp(phase_split), color=GREY, ls=":"); ax[0].text(pd.Timestamp(phase_split), ax[0].get_ylim()[1], " Phase II (monitoring) ->", fontsize=8, va="top")
    ax[0].set_title(title); ax[0].legend(fontsize=7.5, loc="lower left", frameon=False)
    if pct: ax[0].yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1))
    ax[1].plot(ch["mr"].index, ch["mr"].values, lw=0.7, color=GREY); ax[1].axhline(ch["mr_cl"], color=TEAL); ax[1].axhline(ch["mr_ucl"], color=RED, ls="--")
    ax[1].set_title("Moving range", fontsize=9)
    _save(fig, name)


def xbar_s_chart(t: pd.DataFrame, title, name):
    fig, ax = plt.subplots(2, 1, figsize=(11, 5.4), sharex=True)
    x = t.index
    ax[0].plot(x, t["mean"], marker="o", ms=3, lw=0.8, color=NAVY); ax[0].plot(x, t["x_ucl"], "--", color=RED, lw=1); ax[0].plot(x, t["x_lcl"], "--", color=RED, lw=1)
    ax[0].axhline(t["x_cl"].iloc[0], color=TEAL); o = (t["mean"] > t["x_ucl"]) | (t["mean"] < t["x_lcl"])
    ax[0].scatter(x[o], t["mean"][o], color=RED, zorder=3, s=18); ax[0].set_title(title); ax[0].yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1))
    ax[1].plot(x, t["std"], marker="o", ms=3, lw=0.8, color=GREY); ax[1].plot(x, t["s_ucl"], "--", color=RED, lw=1); ax[1].axhline(t["s_cl"].iloc[0], color=TEAL)
    ax[1].set_title("S chart (within-week standard deviation)", fontsize=9)
    _save(fig, name)


def laney_chart(t: pd.DataFrame, title, name, ylabel, scale=1.0):
    fig, ax = plt.subplots(figsize=(11, 3.9))
    ax.plot(t.index, t["rate"] * scale, lw=0.7, color=NAVY, marker="o", ms=2)
    ax.plot(t.index, t["ucl_classic"] * scale, color=GREY, lw=0.6, ls=":", label="classic limits (useless: n is huge)")
    ax.plot(t.index, t["ucl"] * scale, color=RED, lw=1, ls="--", label=f"Laney limits (sigma_z = {t.attrs.get('sigma_z', np.nan):.1f})")
    ax.plot(t.index, t["lcl"] * scale, color=RED, lw=1, ls="--"); ax.axhline(t["cl"].iloc[0] * scale, color=TEAL)
    o = (t["rate"] > t["ucl"]) | (t["rate"] < t["lcl"]); ax.scatter(t.index[o], t["rate"][o] * scale, color=RED, s=14, zorder=3)
    ax.axvline(pd.Timestamp(cfg.PHASE1_END), color=GREY, ls=":")
    ax.set_title(title); ax.set_ylabel(ylabel); ax.legend(fontsize=7.5, frameon=False, loc="upper left")
    _save(fig, name)


def capability_plot(x: pd.Series, cap: dict, lsl, title, name):
    fig, ax = plt.subplots(figsize=(8, 3.8))
    ax.hist(x.dropna(), bins=50, color=TEAL, alpha=0.75, edgecolor="white")
    ax.axvline(lsl, color=RED, lw=2, label=f"LSL {lsl:.0%}"); ax.axvline(cap["mean"], color=NAVY, ls="--", label=f"Mean {cap['mean']:.1%}")
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1))
    txt = f"Ppk = {cap['ppk']:.2f}\nPpk (percentile) = {cap['ppk_percentile_lower']:.2f}\n% days below LSL = {cap['pct_below_lsl']:.1%}\nNormal? {'yes' if cap['normal_at_5pct'] else 'no (A-D)'}"
    ax.text(0.02, 0.95, txt, transform=ax.transAxes, va="top", fontsize=8.5, bbox=dict(fc="white", ec=GREY))
    ax.set_title(title); ax.legend(frameon=False, fontsize=8)
    _save(fig, name)


# ------------------------------------------------------------------ Inventory
def inventory_tradeoff(pol: pd.DataFrame):
    fig, ax = plt.subplots(1, 2, figsize=(11, 3.8))
    for m, g in pol.groupby("equipment_ID"):
        ax[0].plot(g["service_level"], g["safety_stock"] / 1e3, "o-", color=PAL[m], label=m)
        ax[1].plot(g["service_level"], g["total_annual_cost"] / 1e5, "o-", color=PAL[m], label=m)
    ax[0].set_title("Safety stock vs cycle service level"); ax[0].set_ylabel("Safety stock ('000 blanks)")
    ax[1].set_title("Total annual inventory cost vs service level"); ax[1].set_ylabel("INR lakh / year")
    for a in ax: a.set_xlabel("Cycle service level"); a.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1)); a.legend(fontsize=7.5, frameon=False)
    _save(fig, "V01_ss_service_level_tradeoff")


def sawtooth(path: pd.DataFrame, machine):
    fig, ax = plt.subplots(figsize=(11, 3.8))
    ax.plot(path["date"], path["on_hand"] / 1e3, color=NAVY, lw=1, label="On hand")
    ax.axhline(path["rop"].iloc[0] / 1e3, color=ORANGE, ls="--", label="Reorder point"); ax.axhline(path["ss"].iloc[0] / 1e3, color=RED, ls=":", label="Safety stock")
    s = path[path["short"] > 0]; ax.scatter(s["date"], np.zeros(len(s)), color=RED, marker="x", label="Stock-out day")
    ax.set_ylabel("'000 blanks"); ax.legend(ncol=4, fontsize=8, frameon=False, loc="upper right")
    ax.set_title(f"(ROP, EOQ) policy replayed on real 2021 consumption - {machine} (parameters fit on 2020 only)")
    _save(fig, "V02_inventory_sawtooth")


def backtest_plot(static: pd.DataFrame, adaptive: pd.DataFrame):
    fig, ax = plt.subplots(figsize=(8, 3.6))
    x = np.arange(len(static)); w = 0.35
    ax.bar(x - w / 2, static["achieved_CSL"], w, color=GREY, label="Static policy (fit once on 2020)")
    ax.bar(x + w / 2, adaptive["achieved_CSL"], w, color=TEAL, label="Adaptive (monthly re-fit, empirical SS)")
    ax.axhline(cfg.TARGET_SERVICE_LEVEL, color=RED, ls="--", lw=1); ax.set_xticks(x, static["equipment_ID"])
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1)); ax.set_ylabel("Achieved cycle service level (2021)")
    ax.set_title("Out-of-sample backtest vs 98% target"); ax.legend(fontsize=8, frameon=False, loc="lower left")
    _save(fig, "V03_backtest_service_level")
