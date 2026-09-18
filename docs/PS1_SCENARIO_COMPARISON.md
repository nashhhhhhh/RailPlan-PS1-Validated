# PS1 Scenario A/B/C comparison

| Scenario | Workload and ECLO | Capacity | Completion | Primary objective |
|---|---|---|---|---|
| A | Fixed standard accesses; ECLO forbidden | Excess forbidden | Delay allowed | Priority-weighted overrun |
| B | Sufficient scaled workload; ECLO allowed | Excess allowed and penalised | Every contract must meet its planned date | `7 × excess + 5 × ECLO` |
| C | Sufficient scaled workload; ECLO allowed within independent Alpha/Beta two-week windows | At most one excess unit per location/week | Delay allowed | Weighted overrun `+ 7 × excess + 5 × ECLO` |

All scenarios preserve the distinction between network-wide `physical_night`, contract/activity-type/week-local `access_night`, and location/week-local `co_share_group`. They use canonical occupancy and rich physical validation before any organiser files are exposed.

The optimiser history panel loads the latest saved run for A, B and C and displays solver/publication status, each formula and component, over-delivery, hotspots, contract lateness, solve time and physical-validation status. The values are not directly ranked because the objective formulas and feasible regions differ.
