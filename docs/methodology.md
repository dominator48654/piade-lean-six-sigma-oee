# Methodology

## OEE definition and formula
OEE = Availability × Performance × Quality  
where:  
- Availability = Run time / Planned production time  
- Performance = (Actual output / Ideal output) capped at 1.0  
- Quality = Good units / Total units  

In the PIADE dataset, idle time (no reason code) is counted as a loss in availability, following the TPM definition.

## Why idle counts as availability loss
Idle time represents periods when the machine is not running despite being scheduled for production. Since the machine is available but not producing, it is treated as an availability loss rather than a performance or quality loss.

## Counter-delta logic and glitch rule
The PI and PO counters are cumulative counts of input and output packages read at the end of each interval.  
The delta (change) in these counters between intervals represents the number of packages processed in that interval.  
A glitch rule rejects deltas that are negative or exceed a theoretical maximum (based on rated speed × elapsed time) by a factor, indicating counter reset or sensor error.

## Production day and shifts
- Production day: 06:00 UTC to 06:00 UTC (so that a night shift is contained within one day).  
- Shifts (UTC):  
  - A: 06:00–14:00  
  - B: 14:00–22:00  
  - C: 22:00–06:00  

## Stop-event merging (gaps-and-islands)
Consecutive downtime rows with the same alarm code on the same machine are merged into a single stop event.  
The event's start time is the earliest timestamp, and the duration is the sum of elapsed times.

## FMEA scoring scales
Failure Mode and Effects Analysis (FMEA) uses three scales, each from 1–10:  
- Severity (S): impact of the failure mode  
- Occurrence (O): frequency of the cause  
- Detection (D): likelihood of detection before reaching the customer  
Risk Priority Number (RPN) = S × O × D  

## X-bar/R rational-subgroup rationale
Subgroups consist of three shift-level OEE values (one per shift) for a single production day.  
This assumes that the three shifts of a day are produced under similar conditions, allowing the subgroup to represent the process output for that day.  
A day is included only if all three shifts have at least 7,200 seconds of planned time (2 hours per shift).

## Inventory formulas
- Safety stock (SS) = z × √(L × σ_d² + d² × σ_L²)  
- Reorder point (ROP) = d × L + SS  
- Economic order quantity (EOQ) = √(2DS / H)  
where:  
  d = average daily demand  
  L = lead time in days  
  σ_d = standard deviation of daily demand  
  σ_L = standard deviation of lead time  
  D = annual demand  
  S = ordering cost per order  
  H = holding cost per unit per year  
- Kanban container quantity: number of blanks per bin (assumed 2000).  