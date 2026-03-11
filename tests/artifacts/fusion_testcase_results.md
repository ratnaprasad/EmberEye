# Fusion Regression Results (Actual Current Logic)

- Logic source: `FusionOrchestrator` + detectors (unchanged).
- Config used: temp>=40 detect, critical temp>=60 override, smoke>=25, flame>=25, vision>=0.7 gate, temporal fusion disabled.
- Summary: **35/35** match your provided expected column; **0** mismatches.

## Full Results

| Test Case | Vision | Temp | Smoke | Flame | Provided | Actual | Match | Severity | Confidence | Sources | Why Alarm=N (if N) |
|---:|---:|---:|---:|---:|:---:|:---:|:---:|:---:|---:|---|---|
| 1 | 0.7 | 40.0 | 25.0 | 25.0 | Y | Y | PASS | HIGH | 2.1 | smoke;flame;thermal;vision |  |
| 2 | 0.7 | 40.0 | 15.0 | 15.0 | Y | Y | PASS | HIGH | 1.1 | thermal;vision |  |
| 3 | 0.69 | 55.0 | 15.0 | 15.0 | Y | Y | PASS | HIGH | 0.4 | thermal;vision |  |
| 4 | 0.69 | 55.0 | 15.0 | 5.0 | N | N | PASS | NONE | 0.4 | thermal;vision | No fusion rule set alarm=true for this source combination. |
| 5 | 0.69 | 45.0 | 15.0 | 15.0 | N | N | PASS | NONE | 0.4 | thermal;vision | No fusion rule set alarm=true for this source combination. |
| 6 | 0.4 | 55.0 | 15.0 | 15.0 | Y | Y | PASS | HIGH | 0.4 | thermal;vision |  |
| 7 | 0.4 | 55.0 | 15.0 | 5.0 | N | N | PASS | NONE | 0.4 | thermal;vision | No fusion rule set alarm=true for this source combination. |
| 8 | 0.4 | 45.0 | 15.0 | 15.0 | N | N | PASS | NONE | 0.4 | thermal;vision | No fusion rule set alarm=true for this source combination. |
| 9 | 0.29 | 55.0 | 15.0 | 15.0 | Y | Y | PASS | HIGH | 0.4 | thermal;vision |  |
| 10 | 0.29 | 55.0 | 15.0 | 5.0 | N | N | PASS | NONE | 0.4 | thermal;vision | No fusion rule set alarm=true for this source combination. |
| 11 | 0.29 | 45.0 | 15.0 | 15.0 | N | N | PASS | NONE | 0.4 | thermal;vision | No fusion rule set alarm=true for this source combination. |
| 12 | 0.7 | 65.0 | 0.0 | 0.0 | Y | Y | PASS | CRITICAL | 1.0 | thermal;vision |  |
| 13 | 0.7 | 65.0 | 25.0 | 25.0 | Y | Y | PASS | CRITICAL | 1.0 | smoke;flame;thermal;vision |  |
| 14 | 0.5 | 65.0 | 0.0 | 0.0 | Y | Y | PASS | CRITICAL | 1.0 | thermal;vision |  |
| 15 | 0.5 | 55.0 | 25.0 | 0.0 | Y | Y | PASS | HIGH | 0.9 | smoke;thermal;vision |  |
| 16 | 0.5 | 55.0 | 0.0 | 25.0 | Y | Y | PASS | HIGH | 1.0 | flame;thermal;vision |  |
| 17 | 0.5 | 55.0 | 15.0 | 15.0 | Y | Y | PASS | HIGH | 0.4 | thermal;vision |  |
| 18 | 0.5 | 55.0 | 15.0 | 5.0 | N | N | PASS | NONE | 0.4 | thermal;vision | No fusion rule set alarm=true for this source combination. |
| 19 | 0.3 | 55.0 | 15.0 | 15.0 | Y | Y | PASS | HIGH | 0.4 | thermal;vision |  |
| 20 | 0.3 | 55.0 | 15.0 | 5.0 | N | N | PASS | NONE | 0.4 | thermal;vision | No fusion rule set alarm=true for this source combination. |
| 21 | 0.29 | 60.0 | 15.0 | 15.0 | Y | Y | PASS | CRITICAL | 1.0 | thermal;vision |  |
| 22 | 0.69 | 50.0 | 15.0 | 15.0 | N | N | PASS | NONE | 0.4 | thermal;vision | No fusion rule set alarm=true for this source combination. |
| 23 | 0.69 | 50.1 | 15.0 | 15.0 | Y | Y | PASS | HIGH | 0.4 | thermal;vision |  |
| 24 | 0.7 | 50.0 | 19.0 | 19.0 | Y | Y | PASS | HIGH | 1.0 | thermal;vision |  |
| 25 | 0.7 | 50.0 | 20.0 | 19.0 | Y | Y | PASS | HIGH | 1.1 | thermal;vision |  |
| 26 | 0.69 | 55.0 | 15.0 | 9.0 | N | N | PASS | NONE | 0.4 | thermal;vision | No fusion rule set alarm=true for this source combination. |
| 27 | 0.69 | 55.0 | 15.0 | 10.0 | Y | Y | PASS | HIGH | 0.4 | thermal;vision |  |
| 28 | 0.69 | 55.0 | 15.0 | 11.0 | Y | Y | PASS | HIGH | 0.4 | thermal;vision |  |
| 29 | 0.7 | 55.0 | 15.0 | 10.0 | Y | Y | PASS | HIGH | 1.0 | thermal;vision |  |
| 30 | 0.5 | 55.0 | 15.0 | 10.0 | Y | Y | PASS | HIGH | 0.4 | thermal;vision |  |
| 31 | 0.3 | 55.0 | 15.0 | 10.0 | Y | Y | PASS | HIGH | 0.4 | thermal;vision |  |
| 32 | 0.69 | 50.0 | 15.0 | 10.0 | N | N | PASS | NONE | 0.4 | thermal;vision | No fusion rule set alarm=true for this source combination. |
| 33 | 0.69 | 50.1 | 15.0 | 10.0 | Y | Y | PASS | HIGH | 0.4 | thermal;vision |  |
| 34 | 0.3 | 45.0 | 25.0 | 0.0 | Y | Y | PASS | HIGH | 0.9 | smoke;thermal;vision |  |
| 35 | 0.5 | 45.0 | 30.0 | 9.0 | Y | Y | PASS | HIGH | 0.9 | smoke;thermal;vision |  |