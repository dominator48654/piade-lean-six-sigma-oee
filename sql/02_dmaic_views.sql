/* =====================================================================
   PIADE Lean Six Sigma project  |  02_dmaic_views.sql
   All MEASURE / ANALYZE / IMPROVE / CONTROL metrics as SQL views.
   Excel and Power BI read these views directly (or via CSV export).
   ===================================================================== */
SET search_path = piade;

-- =====================================================================
-- MEASURE
-- =====================================================================

-- M1. Daily OEE building blocks per machine (production day 06:00-06:00)
CREATE OR REPLACE VIEW v_daily_machine AS
SELECT equipment_id, prod_date,
       SUM(elapsed_s)                                                  AS logged_s,
       SUM(elapsed_s) FILTER (WHERE state = 'scheduled_downtime')      AS scheduled_downtime_s,
       SUM(elapsed_s) FILTER (WHERE state <> 'scheduled_downtime')     AS planned_s,
       SUM(elapsed_s) FILTER (WHERE is_run)                            AS run_s,
       SUM(elapsed_s) FILTER (WHERE state = 'production')              AS production_s,
       SUM(elapsed_s) FILTER (WHERE state = 'performance_loss')        AS performance_loss_s,
       SUM(elapsed_s) FILTER (WHERE state = 'downtime')                AS downtime_s,
       SUM(elapsed_s) FILTER (WHERE state = 'idle')                    AS idle_s,
       SUM(ideal_units) FILTER (WHERE is_run)                          AS ideal_run_units,
       SUM(d_in)                                                       AS units_in,
       SUM(d_out)                                                      AS units_out,
       COUNT(*) FILTER (WHERE state = 'downtime')                      AS downtime_rows
FROM f_interval
GROUP BY equipment_id, prod_date;

-- M2. OEE per machine + fleet (A x P x Q; idle counted as availability loss)
CREATE OR REPLACE VIEW v_oee_summary AS
WITH b AS (
    SELECT COALESCE(equipment_id,'Fleet') AS equipment_id,
           SUM(logged_s) logged_s, SUM(scheduled_downtime_s) sched_s, SUM(planned_s) planned_s, SUM(run_s) run_s,
           SUM(downtime_s) downtime_s, SUM(idle_s) idle_s, SUM(performance_loss_s) perf_loss_s,
           SUM(ideal_run_units) ideal_units, SUM(units_in) units_in, SUM(units_out) units_out
    FROM v_daily_machine
    GROUP BY ROLLUP (equipment_id)
)
SELECT *,
       run_s / planned_s                                           AS availability,
       LEAST(units_in / ideal_units, 1)                            AS performance,
       units_out / units_in                                        AS quality,
       run_s / planned_s * LEAST(units_in / ideal_units, 1) * units_out / units_in AS oee,
       run_s / logged_s                                            AS utilization
FROM b;

-- M3. Downtime / OEE loss tree (fleet, hours)
CREATE OR REPLACE VIEW v_loss_tree AS
WITH s AS (SELECT * FROM v_oee_summary WHERE equipment_id = 'Fleet'),
pl AS (SELECT SUM(d_in) / SUM(ideal_units) AS eff FROM f_interval WHERE state = 'performance_loss'),
sd AS (SELECT SUM(elapsed_s) FILTER (WHERE elapsed_s BETWEEN 600 AND 14400) AS co_s,
              SUM(elapsed_s) FILTER (WHERE elapsed_s > 14400)            AS long_s,
              SUM(elapsed_s) FILTER (WHERE elapsed_s < 600)              AS short_s
       FROM f_interval WHERE state = 'scheduled_downtime'),
k AS (SELECT s.*, pl.eff, sd.*,
             s.run_s * s.performance            AS net_run_s,
             s.run_s * s.performance * s.quality AS full_s
      FROM s, pl, sd)
SELECT * FROM (
 SELECT 1 ord,'0'   node,'Logged time'                          name, NULL parent, logged_s/3600 hours FROM k UNION ALL
 SELECT 2,'1',  'Scheduled downtime (planned)',           '0',   sched_s/3600 FROM k UNION ALL
 SELECT 3,'1.1','Changeover / cleaning-like (10 min-4 h)','1',   co_s/3600 FROM k UNION ALL
 SELECT 4,'1.2','Long shutdowns (> 4 h)',                 '1',   long_s/3600 FROM k UNION ALL
 SELECT 5,'1.3','Short planned stops (< 10 min)',         '1',   short_s/3600 FROM k UNION ALL
 SELECT 6,'2',  'Planned production time (PPT)',          '0',   planned_s/3600 FROM k UNION ALL
 SELECT 7,'2.1','Availability loss: alarm downtime',      '2',   downtime_s/3600 FROM k UNION ALL
 SELECT 8,'2.2','Availability loss: idle (no reason code)','2',  idle_s/3600 FROM k UNION ALL
 SELECT 9,'3',  'Run time',                               '2',   run_s/3600 FROM k UNION ALL
 SELECT 10,'3.1','Performance loss: reduced speed / minor stops','3', perf_loss_s*(1-eff)/3600 FROM k UNION ALL
 SELECT 11,'3.2','Performance loss: sub-rated running',   '3',   (run_s-net_run_s-perf_loss_s*(1-eff))/3600 FROM k UNION ALL
 SELECT 12,'4', 'Net run time',                           '3',   net_run_s/3600 FROM k UNION ALL
 SELECT 13,'4.1','Quality loss: rejects',                 '4',   (net_run_s-full_s)/3600 FROM k UNION ALL
 SELECT 14,'5', 'Fully productive time (= OEE x PPT)',    '4',   full_s/3600 FROM k
) x
CROSS JOIN (SELECT planned_s/3600 AS ppt_h FROM v_oee_summary WHERE equipment_id='Fleet') p
ORDER BY ord;

-- M4. Pareto of alarm downtime (fleet) with cumulative % and ABC class
CREATE OR REPLACE VIEW v_pareto_alarm AS
WITH a AS (
    SELECT alarm, COUNT(*) AS stops, SUM(duration_s)/3600 AS hours,
           AVG(duration_s)/60 AS mttr_min, COUNT(DISTINCT equipment_id) AS machines
    FROM f_downtime_event GROUP BY alarm
)
SELECT *, hours / SUM(hours) OVER () AS share,
       SUM(hours) OVER (ORDER BY hours DESC ROWS UNBOUNDED PRECEDING) / SUM(hours) OVER () AS cum_share,
       CASE WHEN COALESCE(SUM(hours) OVER (ORDER BY hours DESC ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING),0) / SUM(hours) OVER () < 0.80 THEN 'A'
            WHEN COALESCE(SUM(hours) OVER (ORDER BY hours DESC ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING),0) / SUM(hours) OVER () < 0.95 THEN 'B'
            ELSE 'C' END AS pareto_class,
       RANK() OVER (ORDER BY hours DESC) AS rank_hours
FROM a ORDER BY hours DESC;

-- M5. Pareto per machine (stratification)
CREATE OR REPLACE VIEW v_pareto_alarm_machine AS
SELECT equipment_id, alarm, COUNT(*) stops, SUM(duration_s)/3600 hours,
       RANK() OVER (PARTITION BY equipment_id ORDER BY SUM(duration_s) DESC) AS rank_in_machine
FROM f_downtime_event GROUP BY equipment_id, alarm;

-- M6. Reliability: MTBF / MTTR per machine
CREATE OR REPLACE VIEW v_reliability AS
SELECT e.equipment_id, COUNT(*) stops, SUM(duration_s)/3600 down_h, o.run_s/3600 run_h,
       o.run_s/60 / COUNT(*)         AS mtbf_min,
       SUM(duration_s)/60 / COUNT(*) AS mttr_min,
       (o.run_s/60/COUNT(*)) / (o.run_s/60/COUNT(*) + SUM(duration_s)/60/COUNT(*)) AS inherent_availability
FROM f_downtime_event e JOIN v_oee_summary o USING (equipment_id)
GROUP BY e.equipment_id, o.run_s;

-- M7. Six Sigma baseline: reject DPMO -> sigma level (computed in Excel with NORMSINV)
CREATE OR REPLACE VIEW v_sigma_baseline AS
SELECT equipment_id, units_in AS opportunities, units_in - units_out AS defects,
       (units_in - units_out) / units_in * 1e6 AS dpmo
FROM v_oee_summary;

-- M8. Monthly OEE run chart
CREATE OR REPLACE VIEW v_monthly_oee AS
SELECT equipment_id, date_trunc('month', prod_date)::date AS month,
       SUM(run_s)/SUM(planned_s) * LEAST(SUM(units_in)/SUM(ideal_run_units),1) * SUM(units_out)/SUM(units_in) AS oee
FROM v_daily_machine GROUP BY ROLLUP (date_trunc('month', prod_date)), equipment_id;

-- =====================================================================
-- ANALYZE
-- =====================================================================

-- A1. Shift-level OEE (also the raw material for X-bar / R subgroups)
CREATE OR REPLACE VIEW v_shift_oee AS
SELECT equipment_id, prod_date, shift,
       SUM(elapsed_s) FILTER (WHERE state <> 'scheduled_downtime') AS planned_s,
       SUM(elapsed_s) FILTER (WHERE is_run)                        AS run_s,
       SUM(elapsed_s) FILTER (WHERE state = 'idle')                AS idle_s,
       SUM(elapsed_s) FILTER (WHERE state = 'downtime')            AS downtime_s,
       SUM(ideal_units) FILTER (WHERE is_run)                      AS ideal_units,
       SUM(d_in) AS units_in, SUM(d_out) AS units_out,
       CASE WHEN SUM(elapsed_s) FILTER (WHERE state <> 'scheduled_downtime') > 0
             AND SUM(ideal_units) FILTER (WHERE is_run) > 0 AND SUM(d_in) > 0
            THEN SUM(elapsed_s) FILTER (WHERE is_run) / SUM(elapsed_s) FILTER (WHERE state <> 'scheduled_downtime')
                 * LEAST(SUM(d_in) / SUM(ideal_units) FILTER (WHERE is_run), 1)
                 * LEAST(GREATEST(SUM(d_out) / SUM(d_in), 0), 1)
            ELSE 0 END AS oee
FROM f_interval GROUP BY equipment_id, prod_date, shift;

-- A2. Hypothesis-test inputs: idle and downtime share by shift (per machine-day)
CREATE OR REPLACE VIEW v_shift_state_share AS
SELECT equipment_id, prod_date, shift,
       idle_s / NULLIF(planned_s,0)     AS idle_share,
       downtime_s / NULLIF(planned_s,0) AS downtime_share,
       EXTRACT(isodow FROM prod_date) >= 6 AS is_weekend,
       EXTRACT(year FROM prod_date)::int   AS year
FROM v_shift_oee WHERE planned_s >= 3600;

-- A3. Alarm mix x shift contingency table (chi-square in Excel with CHITEST)
CREATE OR REPLACE VIEW v_alarm_shift_crosstab AS
SELECT CASE WHEN alarm IN ('A_065','A_101','A_006','A_001') THEN alarm ELSE 'other' END AS alarm_group,
       COUNT(*) FILTER (WHERE shift='A') AS shift_a, COUNT(*) FILTER (WHERE shift='B') AS shift_b,
       COUNT(*) FILTER (WHERE shift='C') AS shift_c
FROM f_downtime_event GROUP BY 1 ORDER BY 1;

-- A4. Hour-of-day profile (heat-map input)
CREATE OR REPLACE VIEW v_hourly_profile AS
SELECT hour_utc, state, SUM(elapsed_s)/SUM(SUM(elapsed_s)) OVER (PARTITION BY hour_utc) AS share
FROM f_interval GROUP BY hour_utc, state;

-- A5. FMEA inputs per alarm: MTTR (-> Severity), stops per 1000 run-h (-> Occurrence),
--     repeat-within-30-min rate (-> Detection proxy)
CREATE OR REPLACE VIEW v_fmea_inputs AS
WITH ev AS (
    SELECT *, EXTRACT(epoch FROM ts_start - LAG(ts_start) OVER (PARTITION BY equipment_id, alarm ORDER BY ts_start)) AS gap_same_s
    FROM f_downtime_event
), runh AS (SELECT equipment_id, run_s/3600 run_h FROM v_oee_summary)
SELECT ev.alarm, COUNT(*) stops, SUM(duration_s)/3600 downtime_h, AVG(duration_s)/60 mttr_min,
       COUNT(*) * 1000.0 / (SELECT SUM(run_h) FROM runh r WHERE r.equipment_id IN (SELECT DISTINCT equipment_id FROM f_downtime_event x WHERE x.alarm = ev.alarm)) AS stops_per_1000_run_h,
       AVG(CASE WHEN gap_same_s <= 1800 THEN 1.0 ELSE 0 END) AS repeat_within_30min,
       string_agg(DISTINCT equipment_id, ', ') AS machines
FROM ev GROUP BY ev.alarm ORDER BY downtime_h DESC;

-- =====================================================================
-- IMPROVE
-- =====================================================================

-- I1. SMED baseline: changeover-like planned stops (10 min - 4 h)
CREATE OR REPLACE VIEW v_smed_baseline AS
SELECT equipment_id, COUNT(*) AS events,
       AVG(elapsed_s)/60 AS mean_min,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY elapsed_s)/60 AS median_min,
       percentile_cont(0.9) WITHIN GROUP (ORDER BY elapsed_s)/60 AS p90_min,
       SUM(elapsed_s)/3600 AS hours
FROM f_interval
WHERE state = 'scheduled_downtime'
  AND elapsed_s BETWEEN (SELECT value FROM cfg_param WHERE key='changeover_min_s') AND (SELECT value FROM cfg_param WHERE key='changeover_max_s')
GROUP BY equipment_id;

-- I2. Daily packaging-material demand (1 blank per input package), zero-filled calendar days
CREATE OR REPLACE VIEW v_material_demand AS
WITH span AS (SELECT equipment_id, MIN(cal_date) d0, MAX(cal_date) d1 FROM f_interval GROUP BY equipment_id),
cal AS (SELECT equipment_id, generate_series(d0, d1, interval '1 day')::date AS cal_date FROM span),
use_ AS (SELECT equipment_id, cal_date, SUM(d_in) demand FROM f_interval GROUP BY equipment_id, cal_date)
SELECT c.equipment_id, c.cal_date, COALESCE(u.demand,0) AS demand
FROM cal c LEFT JOIN use_ u USING (equipment_id, cal_date);

-- I3. Inventory policy: Safety stock / ROP / EOQ by service level
--     Parameters estimated on Phase I (2020); machines with < 60 days in 2020 use their first half.
CREATE OR REPLACE VIEW v_inventory_policy AS
WITH p AS (SELECT MAX(value) FILTER (WHERE key='lead_time_days') L, MAX(value) FILTER (WHERE key='lead_time_sd_days') sL,
                  MAX(value) FILTER (WHERE key='order_cost_inr') S, MAX(value) FILTER (WHERE key='pkg_unit_cost_inr') c,
                  MAX(value) FILTER (WHERE key='holding_rate') h FROM cfg_param),
span AS (SELECT equipment_id, MIN(cal_date) d0, MAX(cal_date) d1,
                COUNT(*) FILTER (WHERE cal_date <= '2020-12-31') n2020 FROM v_material_demand GROUP BY equipment_id),
tr AS (SELECT m.equipment_id, AVG(demand) d, STDDEV_SAMP(demand) sd, COUNT(*) train_days
       FROM v_material_demand m JOIN span s USING (equipment_id)
       WHERE m.cal_date <= CASE WHEN s.n2020 >= 60 THEN '2020-12-31'::date ELSE s.d0 + (s.d1 - s.d0)/2 END
       GROUP BY m.equipment_id)
SELECT tr.equipment_id, z.service_level, z.z, tr.train_days, tr.d AS mean_daily, tr.sd AS sd_daily,
       sqrt(p.L*tr.sd^2 + tr.d^2*p.sL^2)                                AS sigma_ltd,
       z.z * sqrt(p.L*tr.sd^2 + tr.d^2*p.sL^2)                          AS safety_stock,
       tr.d*p.L + z.z * sqrt(p.L*tr.sd^2 + tr.d^2*p.sL^2)               AS reorder_point,
       sqrt(2 * tr.d*365 * p.S / (p.c*p.h))                             AS eoq,
       tr.d*365 / sqrt(2 * tr.d*365 * p.S / (p.c*p.h))                  AS orders_per_year,
       p.c*p.h * (sqrt(2 * tr.d*365 * p.S / (p.c*p.h))/2 + z.z * sqrt(p.L*tr.sd^2 + tr.d^2*p.sL^2))
         + tr.d*365 / sqrt(2 * tr.d*365 * p.S / (p.c*p.h)) * p.S        AS total_annual_cost_inr
FROM tr CROSS JOIN p CROSS JOIN z_table z
WHERE z.service_level IN (0.90, 0.95, 0.98, 0.99);

-- I4. Kanban sizing: N = D x L x (1 + alpha) / C  (average and rated-speed draw)
CREATE OR REPLACE VIEW v_kanban AS
WITH p AS (SELECT MAX(value) FILTER (WHERE key='kanban_container_qty') C, MAX(value) FILTER (WHERE key='kanban_replen_hours') L,
                  MAX(value) FILTER (WHERE key='kanban_safety_factor') a FROM cfg_param)
SELECT o.equipment_id, o.units_in / (o.planned_s/3600) AS avg_draw_per_h, o.ideal_units / (o.run_s/3600) AS rated_draw_per_h,
       CEIL(o.units_in / (o.planned_s/3600) * p.L * (1+p.a) / p.C) AS kanbans_avg,
       CEIL(o.ideal_units / (o.run_s/3600) * p.L * (1+p.a) / p.C)  AS kanbans_peak
FROM v_oee_summary o CROSS JOIN p WHERE o.equipment_id <> 'Fleet';

-- =====================================================================
-- CONTROL: X-bar / R chart
-- Rational subgroup = one production day; n = 3 shift-level OEE values (A, B, C).
-- X-bar tracks day-to-day level; R tracks shift-to-shift inconsistency.
-- Only days where all 3 shifts had >= 2 h planned time enter the chart.
-- Phase I limits from 2020, Phase II (2021) is monitored against them.
-- =====================================================================
CREATE OR REPLACE VIEW v_xbar_r_subgroups AS
SELECT equipment_id, prod_date,
       MAX(oee) FILTER (WHERE shift='A') AS oee_a,
       MAX(oee) FILTER (WHERE shift='B') AS oee_b,
       MAX(oee) FILTER (WHERE shift='C') AS oee_c,
       AVG(oee)             AS xbar,
       MAX(oee) - MIN(oee)  AS r,
       COUNT(*)             AS n,
       CASE WHEN prod_date <= '2020-12-31' THEN 'Phase I' ELSE 'Phase II' END AS phase
FROM v_shift_oee
WHERE planned_s >= (SELECT value FROM cfg_param WHERE key = 'min_shift_planned_s')
GROUP BY equipment_id, prod_date
HAVING COUNT(*) = 3;

CREATE OR REPLACE VIEW v_xbar_r_limits AS
SELECT s.equipment_id, COUNT(*) AS phase1_subgroups, AVG(xbar) AS xbarbar, AVG(r) AS rbar,
       AVG(xbar) + c.a2*AVG(r) AS ucl_x, AVG(xbar) - c.a2*AVG(r) AS lcl_x,
       c.d4*AVG(r) AS ucl_r, c.d3*AVG(r) AS lcl_r, AVG(r)/c.d2 AS sigma_within
FROM v_xbar_r_subgroups s JOIN spc_constants c ON c.n = 3
WHERE s.phase = 'Phase I'
GROUP BY s.equipment_id, c.a2, c.d3, c.d4, c.d2;

CREATE OR REPLACE VIEW v_xbar_r_chart AS
WITH j AS (
    SELECT s.*, l.xbarbar, l.rbar, l.ucl_x, l.lcl_x, l.ucl_r, l.lcl_r, l.sigma_within,
           SIGN(s.xbar - l.xbarbar) AS side
    FROM v_xbar_r_subgroups s JOIN v_xbar_r_limits l USING (equipment_id)
)
SELECT *,
       (xbar > ucl_x OR xbar < lcl_x)  AS x_rule1_out,
       (r > ucl_r)                     AS r_rule1_out,
       ABS(SUM(side) OVER (PARTITION BY equipment_id ORDER BY prod_date ROWS 7 PRECEDING)) = 8 AS x_rule_8_same_side
FROM j ORDER BY equipment_id, prod_date;

-- Capability of the pilot (Ppk vs OEE target; Cpk uses R-bar/d2 within-subgroup sigma)
DROP VIEW IF EXISTS v_capability;
CREATE VIEW v_capability AS
SELECT l.equipment_id, t.value::float8 AS lsl, AVG(s.xbar)::float8 AS mean_xbar, STDDEV_SAMP(s.xbar)::float8 AS sd_overall,
       l.sigma_within::float8 AS sigma_within,
       ((AVG(s.xbar) - t.value) / (3*STDDEV_SAMP(s.xbar)))::float8 AS ppk_daily,
       ((AVG(s.xbar) - t.value) / (3*l.sigma_within))::float8      AS cpk_shift_level,
       AVG(CASE WHEN s.xbar < t.value THEN 1.0 ELSE 0 END)::float8  AS pct_days_below_target
FROM v_xbar_r_subgroups s JOIN v_xbar_r_limits l USING (equipment_id)
CROSS JOIN (SELECT value FROM cfg_param WHERE key='oee_target') t
GROUP BY l.equipment_id, t.value, l.sigma_within;
-- NOTE: v_xbar_r_limits = Pass-1 limits (all of 2020). Excel tab C1 adds the revised pass
-- (assignable-cause candidates removed): CL 67.3%, UCL 95.9%, LCL 38.6%, UCL_R 72.1% for s_1.
