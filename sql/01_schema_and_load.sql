/* =====================================================================
   PIADE Lean Six Sigma project  |  01_schema_and_load.sql  (PostgreSQL 14+)
   DMAIC phase: MEASURE (data collection plan + data-integrity checks)

   Run from the folder that contains raw_data.csv:
       psql -d piade -v ON_ERROR_STOP=1 -f 01_schema_and_load.sql
   ===================================================================== */

DROP SCHEMA IF EXISTS piade CASCADE;
CREATE SCHEMA piade;
SET search_path = piade;

-- ---------------------------------------------------------------------
-- 1. Staging table: exact copy of the Kaggle file (no transformations)
-- ---------------------------------------------------------------------
CREATE TABLE stg_raw (
    interval_start  text,
    equipment_id    text,
    alarm           text,
    type            text,
    start_epoch     double precision,   -- unix seconds
    end_epoch       double precision,
    elapsed_ms      bigint,             -- NOTE: milliseconds (verified: elapsed/(end-start) = 1000)
    pi              bigint,             -- cumulative INPUT counter, read at interval END
    po              bigint,             -- cumulative OUTPUT counter, read at interval END
    speed           integer             -- rated speed, packages / hour
);

\copy stg_raw FROM 'data/raw/raw_data.csv' WITH (FORMAT csv, HEADER true)

-- ---------------------------------------------------------------------
-- 2. Assumption / parameter table  (edit here, every view follows)
-- ---------------------------------------------------------------------
CREATE TABLE cfg_param (key text PRIMARY KEY, value numeric, note text);
INSERT INTO cfg_param VALUES
 ('oee_target',             0.65,   'Project goal (world class = 0.85)'),
 ('quality_lsl',            0.990,  'Daily quality lower spec limit'),
 ('pkg_unit_cost_inr',      4.0,    'ASSUMPTION: cost per carton blank'),
 ('order_cost_inr',         6000,   'ASSUMPTION: cost to place + receive one PO'),
 ('holding_rate',           0.24,   'ASSUMPTION: annual holding cost fraction'),
 ('lead_time_days',         7,      'ASSUMPTION: supplier lead time'),
 ('lead_time_sd_days',      1.5,    'ASSUMPTION: lead-time standard deviation'),
 ('kanban_container_qty',   2000,   'ASSUMPTION: blanks per bin / pallet'),
 ('kanban_replen_hours',    8,      'ASSUMPTION: line-side replenishment loop'),
 ('kanban_safety_factor',   0.15,   'ASSUMPTION: Kanban safety factor alpha'),
 ('changeover_min_s',       600,    'ASSUMPTION: planned stop >= 10 min = changeover-like'),
 ('changeover_max_s',       14400,  'ASSUMPTION: planned stop <= 4 h  = changeover-like'),
 ('min_shift_planned_s',    7200,   'Shift needs >= 2 h planned time to enter X-bar/R subgroup');

-- z-values for cycle service levels (PostgreSQL has no inverse-normal function)
CREATE TABLE z_table (service_level numeric PRIMARY KEY, z numeric);
INSERT INTO z_table VALUES (0.90,1.2816),(0.95,1.6449),(0.975,1.9600),(0.98,2.0537),(0.99,2.3263),(0.995,2.5758),(0.999,3.0902);

-- Shewhart constants for X-bar / R charts (AIAG SPC manual)
CREATE TABLE spc_constants (n int PRIMARY KEY, a2 numeric, d3 numeric, d4 numeric, d2 numeric);
INSERT INTO spc_constants VALUES
 (2,1.880,0,3.267,1.128),(3,1.023,0,2.574,1.693),(4,0.729,0,2.282,2.059),(5,0.577,0,2.114,2.326),
 (6,0.483,0,2.004,2.534),(7,0.419,0.076,1.924,2.704),(8,0.373,0.136,1.864,2.847),(9,0.337,0.184,1.816,2.970),(10,0.308,0.223,1.777,3.078);

-- ---------------------------------------------------------------------
-- 3. Clean interval fact: typed, counter deltas, shift, production day
--    Production day runs 06:00 -> 06:00 so the 3 shifts of one day
--    (A 06-14, B 14-22, C 22-06) form one rational subgroup.
-- ---------------------------------------------------------------------
CREATE TABLE f_interval AS
WITH t AS (
    SELECT equipment_id,
           NULLIF(alarm,'A_000')                          AS alarm,
           type                                           AS state,
           to_timestamp(start_epoch)                      AS ts_start,
           to_timestamp(end_epoch)                        AS ts_end,
           elapsed_ms / 1000.0                            AS elapsed_s,
           speed,
           pi, po,
           pi - LAG(pi) OVER w                            AS d_in_raw,
           po - LAG(po) OVER w                            AS d_out_raw,
           LAG(type) OVER w                               AS prev_state,
           LAG(alarm) OVER w                              AS prev_alarm_raw,
           ROW_NUMBER() OVER w                            AS seq
    FROM stg_raw
    WINDOW w AS (PARTITION BY equipment_id ORDER BY start_epoch)
)
SELECT t.*,
       speed * elapsed_s / 3600.0                                                   AS ideal_units,
       (d_in_raw >= 0 AND d_out_raw >= 0 AND d_in_raw <= 3 * speed * elapsed_s / 3600.0 + 500) AS counter_valid,
       CASE WHEN d_in_raw >= 0 AND d_out_raw >= 0 AND d_in_raw <= 3 * speed * elapsed_s / 3600.0 + 500 THEN d_in_raw  END AS d_in,
       CASE WHEN d_in_raw >= 0 AND d_out_raw >= 0 AND d_in_raw <= 3 * speed * elapsed_s / 3600.0 + 500 THEN d_out_raw END AS d_out,
       state IN ('production','performance_loss')                                  AS is_run,
       EXTRACT(hour FROM ts_start AT TIME ZONE 'UTC')::int                          AS hour_utc,
       CASE WHEN EXTRACT(hour FROM ts_start AT TIME ZONE 'UTC') BETWEEN 6 AND 13 THEN 'A'
            WHEN EXTRACT(hour FROM ts_start AT TIME ZONE 'UTC') BETWEEN 14 AND 21 THEN 'B'
            ELSE 'C' END                                                            AS shift,
       ((ts_start AT TIME ZONE 'UTC') - interval '6 hours')::date                   AS prod_date,
       (ts_start AT TIME ZONE 'UTC')::date                                          AS cal_date
FROM t;

CREATE INDEX ix_int_machine_date ON f_interval (equipment_id, prod_date);
CREATE INDEX ix_int_state        ON f_interval (state);
ANALYZE f_interval;

-- ---------------------------------------------------------------------
-- 4. Downtime EVENTS (gaps-and-islands: consecutive downtime rows with
--    the same alarm on the same machine = one stop)
-- ---------------------------------------------------------------------
CREATE TABLE f_downtime_event AS
WITH flagged AS (
    SELECT *,
           CASE WHEN state = 'downtime' AND prev_state = 'downtime'
                     AND alarm IS NOT DISTINCT FROM NULLIF(prev_alarm_raw,'A_000') THEN 0 ELSE 1 END AS new_event
    FROM f_interval
), grp AS (
    SELECT *, SUM(new_event) OVER (PARTITION BY equipment_id ORDER BY seq) AS event_no
    FROM flagged
)
SELECT equipment_id, event_no, alarm,
       MIN(ts_start)            AS ts_start,
       MIN(prod_date)           AS prod_date,
       MIN(shift)               AS shift,
       SUM(elapsed_s)           AS duration_s,
       MIN(prev_state)          AS preceding_state
FROM grp
WHERE state = 'downtime'
GROUP BY equipment_id, event_no, alarm;

-- ---------------------------------------------------------------------
-- 5. Dimensions for Power BI star schema
-- ---------------------------------------------------------------------
CREATE TABLE dim_machine AS
SELECT equipment_id,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY speed) AS rated_speed_median,
       MIN(ts_start) AS first_ts, MAX(ts_end) AS last_ts,
       (equipment_id = 's_1') AS is_pilot
FROM f_interval GROUP BY equipment_id;

CREATE TABLE dim_date AS
SELECT d::date AS date_key,
       EXTRACT(year FROM d)::int AS year, EXTRACT(month FROM d)::int AS month,
       to_char(d,'Mon') AS month_name, EXTRACT(isodow FROM d)::int AS iso_dow,
       to_char(d,'Dy') AS weekday, EXTRACT(isodow FROM d) >= 6 AS is_weekend,
       CASE WHEN d <= '2020-12-31' THEN 'Phase I (baseline)' ELSE 'Phase II (monitor)' END AS spc_phase
FROM generate_series('2019-12-31'::date, '2022-01-02'::date, interval '1 day') d;

-- ---------------------------------------------------------------------
-- 6. Data-integrity report (MSA substitute: logs cannot be re-measured)
-- ---------------------------------------------------------------------
CREATE VIEW v_data_quality AS
SELECT 'rows loaded' AS check_name, COUNT(*)::numeric AS result FROM stg_raw
UNION ALL SELECT 'null cells in key columns', COUNT(*) FILTER (WHERE equipment_id IS NULL OR type IS NULL OR elapsed_ms IS NULL) FROM stg_raw
UNION ALL SELECT 'duplicate rows', COUNT(*) - COUNT(DISTINCT (equipment_id, start_epoch, type, alarm)) FROM stg_raw
UNION ALL SELECT 'elapsed vs (end-start) mismatch > 1 %', COUNT(*) FILTER (WHERE abs(elapsed_ms/1000.0 - (end_epoch-start_epoch)) > 0.01*elapsed_ms/1000.0 + 0.01) FROM stg_raw
UNION ALL SELECT 'negative counter deltas (pi)', COUNT(*) FILTER (WHERE d_in_raw < 0) FROM f_interval
UNION ALL SELECT 'counter deltas rejected as glitch', COUNT(*) FILTER (WHERE NOT counter_valid) FROM f_interval
UNION ALL SELECT 'alarm on non-downtime row', COUNT(*) FILTER (WHERE alarm IS NOT NULL AND state <> 'downtime') FROM f_interval
UNION ALL SELECT 'downtime row without alarm', COUNT(*) FILTER (WHERE alarm IS NULL AND state = 'downtime') FROM f_interval
UNION ALL SELECT 'idle rows with a reason code', COUNT(*) FILTER (WHERE alarm IS NOT NULL AND state = 'idle') FROM f_interval;
