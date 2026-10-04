# Assumptions

The following assumptions are used in the PIADE Lean Six Sigma DMAIC project.  
These are drawn from the Excel "Inputs" tab and the SQL `cfg_param` table.

| Assumption | Value | Unit | Source / note |
|------------|-------|------|---------------|
| OEE target (project goal) | 0.65 | fraction | Project goal; world-class benchmark is 0.85 |
| Quality LSL (daily good / total) | 0.990 | fraction | Assumed customer requirement |
| Contribution per good pack | 0.60 | INR | ASSUMPTION - replace with finance data |
| Study period | 2.0 | years | Jan 2020 - Dec 2021 (731 days) |
| Packaging blank unit cost | 4.0 | INR | ASSUMPTION |
| Ordering cost per PO | 6000 | INR | ASSUMPTION |
| Annual holding rate | 0.24 | fraction | ASSUMPTION (capital + storage + obsolescence) |
| Supplier lead time | 7 | days | ASSUMPTION |
| Lead-time standard deviation | 1.5 | days | ASSUMPTION |
| Target cycle service level | 0.98 | fraction | Policy choice |
| Kanban container quantity | 2000 | blanks/bin | ASSUMPTION |
| Kanban replenishment lead time | 8 | hours | ASSUMPTION (one shift) |
| Kanban safety factor (alpha) | 0.15 | fraction | ASSUMPTION |
| SMED target reduction in changeover time | 0.40 | fraction | Typical first SMED pass: 30-50% |
| Spare-kit lead time | 21 | days | ASSUMPTION |
| Spare-kit service level | 0.95 | fraction | Policy choice |
| Spare-kit unit cost | 18000 | INR | ASSUMPTION |
| Spare-kit ordering cost | 2500 | INR | ASSUMPTION |
| Spare-kit holding rate | 0.20 | fraction | ASSUMPTION |