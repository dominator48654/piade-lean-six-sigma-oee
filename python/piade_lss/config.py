"""Project-wide settings and documented assumptions.

Every number here that is not derived from the PIADE data is an ASSUMPTION
and is labelled as such. Change it here and the whole pipeline follows.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]          # project/
DATA_DIR = ROOT / "data"                             # put raw_data.csv + sequences_1h_data.csv here
OUT_DIR = ROOT / "outputs"
FIG_DIR = OUT_DIR / "figures"
TAB_DIR = OUT_DIR / "tables"
BI_DIR = OUT_DIR / "powerbi"

MACHINES = ["s_1", "s_2", "s_3", "s_4", "s_5"]
STATES = ["production", "performance_loss", "downtime", "idle", "scheduled_downtime"]

# --- Measurement-system rules (data integrity) ---------------------------
# pi/po are cumulative counters read at interval END (verified: delta vs
# speed*elapsed correlation r=0.95 on production rows). A delta is rejected
# as a counter reset / glitch when negative or > 3x theoretical + 500.
COUNTER_GLITCH_FACTOR = 3.0
COUNTER_GLITCH_SLACK = 500

# --- Phase split for SPC ---------------------------------------------------
PHASE1_END = "2020-12-31"      # Phase I (baseline limits) = 2020, Phase II = 2021

# --- Shift blocks (ASSUMPTION: timestamps are UTC, 3 x 8h shifts) --------
SHIFTS = {"A (06-14)": range(6, 14), "B (14-22)": range(14, 22), "C (22-06)": list(range(22, 24)) + list(range(0, 6))}

# --- CTQ targets (ASSUMPTION: typical FMCG packaging benchmarks) ---------
OEE_TARGET = 0.65              # project goal, stretch vs world-class 0.85
QUALITY_LSL = 0.990            # daily good/total must stay >= 99.0 %

# --- SMED: which scheduled stops look like changeovers (ASSUMPTION) -------
CHANGEOVER_MIN_S = 10 * 60     # 10 min .. 4 h scheduled stops treated as
CHANGEOVER_MAX_S = 4 * 3600    # changeover / cleaning / format-change events

# --- Inventory assumptions (ASSUMPTION - replace with plant master data) -
# Packaging material = 1 blank/carton per input package (pi).
PKG_UNIT_COST_INR = 4.0        # cost per blank (INR)
ORDER_COST_INR = 6000.0        # cost to place + receive one PO (INR)
HOLDING_RATE = 0.24            # annual holding cost as fraction of unit cost
PKG_LEAD_TIME_DAYS = 7         # supplier lead time (days)
PKG_LEAD_TIME_SD_DAYS = 1.5    # lead-time std-dev (days)
SERVICE_LEVELS = [0.90, 0.95, 0.98, 0.99]
TARGET_SERVICE_LEVEL = 0.98    # cycle service level for packaging material
WORKING_DAYS_PER_YEAR = 330

# Spare parts (critical failure modes -> spare kit demand)
SPARE_LEAD_TIME_DAYS = 21
SPARE_UNIT_COST_INR = 18000.0
SPARE_ORDER_COST_INR = 2500.0
SPARE_HOLDING_RATE = 0.20
SPARE_KIT_EVENT_MIN_S = 30 * 60   # a stop >= 30 min on a top alarm is assumed to consume 1 spare kit
SPARE_SERVICE_LEVEL = 0.95

# Kanban (line-side packaging material)
KANBAN_CONTAINER_QTY = 2000    # blanks per pallet/bin
KANBAN_REPLEN_HOURS = 8        # line-side replenishment lead time (h)
KANBAN_SAFETY_FACTOR = 0.15

# --- Financial assumptions (ASSUMPTION) ------------------------------------
CONTRIBUTION_PER_PACK_INR = 0.60   # contribution margin per good package (INR)
