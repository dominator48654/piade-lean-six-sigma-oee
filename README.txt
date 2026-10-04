PIADE Lean Six Sigma (DMAIC) project - Packaging-machine OEE
============================================================
Stack: PostgreSQL (engine) -> Excel (DMAIC analysis) -> Power BI (control cockpit). Python optional.

1. report/PIADE_LSS_DMAIC_Project_Guide.docx  <- START HERE: phase-by-phase procedure, results, 4-week plan, interview points
2. sql/01_schema_and_load.sql   load raw_data.csv, clean intervals, stop events, dimensions, data-quality checks
   sql/02_dmaic_views.sql       25 views for Measure / Analyze / Improve / Control (incl. X-bar & R)
   sql/03_export.sql            export all views to CSV (x_*.csv)
   Run: createdb piade ; psql -d piade -f 01_schema_and_load.sql ; psql -d piade -f 02_dmaic_views.sql ; psql -d piade -f 03_export.sql
   (put raw_data.csv in the same folder as the .sql files)
3. excel/PIADE_LSS_DMAIC_Workbook.xlsx   28 tabs in DMAIC order, 16,600+ live formulas, 0 errors. Yellow = assumptions (Inputs tab).
   excel/build_workbook.py               rebuilds the workbook from the x_*.csv exports
4. powerbi/PIADE_PowerBI_measures.dax    Power Query, relationships, DAX measures, page plan
   powerbi/*.csv                         ready-made star-schema tables if you skip PostgreSQL
5. data_exports/x_*.csv                  SQL view outputs (what the Excel Data tabs contain)
6. python/ (optional)                    run_pipeline.py regenerates figures + inventory backtest
7. figures/                              all charts used in the report

Honesty: Improve-phase gains are projections from assumed reduction rates, not implemented results.
