/* PIADE LSS | 03_export.sql - export every view to CSV for Excel / Power BI
   psql -d piade -f 03_export.sql   (writes into the current folder) */
SET search_path = piade;
\copy (SELECT * FROM v_data_quality)                              TO 'data/exports/x_data_quality.csv' CSV HEADER
\copy (SELECT * FROM v_daily_machine ORDER BY 1,2)                TO 'data/exports/x_daily_machine.csv' CSV HEADER
\copy (SELECT * FROM v_oee_summary)                               TO 'data/exports/x_oee_summary.csv' CSV HEADER
\copy (SELECT * FROM v_loss_tree)                                 TO 'data/exports/x_loss_tree.csv' CSV HEADER
\copy (SELECT * FROM v_pareto_alarm)                              TO 'data/exports/x_pareto_alarm.csv' CSV HEADER
\copy (SELECT * FROM v_pareto_alarm_machine WHERE rank_in_machine <= 10) TO 'data/exports/x_pareto_machine.csv' CSV HEADER
\copy (SELECT * FROM v_reliability)                               TO 'data/exports/x_reliability.csv' CSV HEADER
\copy (SELECT * FROM v_monthly_oee WHERE month IS NOT NULL ORDER BY 2,1) TO 'data/exports/x_monthly_oee.csv' CSV HEADER
\copy (SELECT * FROM v_shift_state_share ORDER BY 1,2,3)          TO 'data/exports/x_shift_state_share.csv' CSV HEADER
\copy (SELECT * FROM v_alarm_shift_crosstab)                      TO 'data/exports/x_alarm_shift.csv' CSV HEADER
\copy (SELECT * FROM v_fmea_inputs LIMIT 10)                      TO 'data/exports/x_fmea_inputs.csv' CSV HEADER
\copy (SELECT * FROM v_smed_baseline ORDER BY 1)                  TO 'data/exports/x_smed.csv' CSV HEADER
\copy (SELECT * FROM v_material_demand ORDER BY 1,2)              TO 'data/exports/x_material_demand.csv' CSV HEADER
\copy (SELECT * FROM v_inventory_policy ORDER BY 1,2)             TO 'data/exports/x_inventory_policy.csv' CSV HEADER
\copy (SELECT * FROM v_kanban ORDER BY 1)                         TO 'data/exports/x_kanban.csv' CSV HEADER
\copy (SELECT * FROM v_xbar_r_chart WHERE equipment_id = 's_1' ORDER BY prod_date) TO 'data/exports/x_xbar_r_s1.csv' CSV HEADER
\copy (SELECT * FROM v_xbar_r_chart ORDER BY 1,2)                 TO 'data/exports/x_xbar_r_all.csv' CSV HEADER
\copy (SELECT * FROM v_xbar_r_limits ORDER BY 1)                  TO 'data/exports/x_xbar_r_limits.csv' CSV HEADER
\copy (SELECT * FROM v_capability ORDER BY 1)                     TO 'data/exports/x_capability.csv' CSV HEADER
\copy (SELECT * FROM v_sigma_baseline)                            TO 'data/exports/x_sigma.csv' CSV HEADER
\copy (SELECT * FROM v_hourly_profile ORDER BY 1,2)               TO 'data/exports/x_hourly_profile.csv' CSV HEADER
