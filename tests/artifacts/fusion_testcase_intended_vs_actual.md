# Fusion Intended Rules vs Actual Logic

- Intended rules are taken from your regression specification (independent 60/20/20 + vision-banded conditions).
- Provided vs Intended mismatches: **0**
- Intended vs Actual mismatches: **0**

## Full Table

| Test Case | Vision | Temp | Smoke | Flame | Provided | Intended | Actual | PvsI | IvsA | Rule Path |
|---:|---:|---:|---:|---:|:---:|:---:|:---:|:---:|:---:|---|
| 1 | 0.7 | 40.0 | 25.0 | 25.0 | Y | Y | Y | PASS | PASS | independent_trigger |
| 2 | 0.7 | 40.0 | 15.0 | 15.0 | Y | Y | Y | PASS | PASS | vision>=0.70 |
| 3 | 0.69 | 55.0 | 15.0 | 15.0 | Y | Y | Y | PASS | PASS | 0.50<=vision<0.70 and temp>50 and flame>=10 |
| 4 | 0.69 | 55.0 | 15.0 | 5.0 | N | N | N | PASS | PASS | 0.50<=vision<0.70 but temp/flame condition failed |
| 5 | 0.69 | 45.0 | 15.0 | 15.0 | N | N | N | PASS | PASS | 0.50<=vision<0.70 but temp/flame condition failed |
| 6 | 0.4 | 55.0 | 15.0 | 15.0 | Y | Y | Y | PASS | PASS | 0.30<=vision<0.50 and temp>50 and flame>=10 |
| 7 | 0.4 | 55.0 | 15.0 | 5.0 | N | N | N | PASS | PASS | 0.30<=vision<0.50 but temp/flame condition failed |
| 8 | 0.4 | 45.0 | 15.0 | 15.0 | N | N | N | PASS | PASS | 0.30<=vision<0.50 but temp/flame condition failed |
| 9 | 0.29 | 55.0 | 15.0 | 15.0 | Y | Y | Y | PASS | PASS | vision<0.30 and temp>50 and flame>=10 |
| 10 | 0.29 | 55.0 | 15.0 | 5.0 | N | N | N | PASS | PASS | vision<0.30 and temp/flame condition failed |
| 11 | 0.29 | 45.0 | 15.0 | 15.0 | N | N | N | PASS | PASS | vision<0.30 and temp/flame condition failed |
| 12 | 0.7 | 65.0 | 0.0 | 0.0 | Y | Y | Y | PASS | PASS | independent_trigger |
| 13 | 0.7 | 65.0 | 25.0 | 25.0 | Y | Y | Y | PASS | PASS | independent_trigger |
| 14 | 0.5 | 65.0 | 0.0 | 0.0 | Y | Y | Y | PASS | PASS | independent_trigger |
| 15 | 0.5 | 55.0 | 25.0 | 0.0 | Y | Y | Y | PASS | PASS | independent_trigger |
| 16 | 0.5 | 55.0 | 0.0 | 25.0 | Y | Y | Y | PASS | PASS | independent_trigger |
| 17 | 0.5 | 55.0 | 15.0 | 15.0 | Y | Y | Y | PASS | PASS | 0.50<=vision<0.70 and temp>50 and flame>=10 |
| 18 | 0.5 | 55.0 | 15.0 | 5.0 | N | N | N | PASS | PASS | 0.50<=vision<0.70 but temp/flame condition failed |
| 19 | 0.3 | 55.0 | 15.0 | 15.0 | Y | Y | Y | PASS | PASS | 0.30<=vision<0.50 and temp>50 and flame>=10 |
| 20 | 0.3 | 55.0 | 15.0 | 5.0 | N | N | N | PASS | PASS | 0.30<=vision<0.50 but temp/flame condition failed |
| 21 | 0.29 | 60.0 | 15.0 | 15.0 | Y | Y | Y | PASS | PASS | independent_trigger |
| 22 | 0.69 | 50.0 | 15.0 | 15.0 | N | N | N | PASS | PASS | 0.50<=vision<0.70 but temp/flame condition failed |
| 23 | 0.69 | 50.1 | 15.0 | 15.0 | Y | Y | Y | PASS | PASS | 0.50<=vision<0.70 and temp>50 and flame>=10 |
| 24 | 0.7 | 50.0 | 19.0 | 19.0 | Y | Y | Y | PASS | PASS | vision>=0.70 |
| 25 | 0.7 | 50.0 | 20.0 | 19.0 | Y | Y | Y | PASS | PASS | independent_trigger |
| 26 | 0.69 | 55.0 | 15.0 | 9.0 | N | N | N | PASS | PASS | 0.50<=vision<0.70 but temp/flame condition failed |
| 27 | 0.69 | 55.0 | 15.0 | 10.0 | Y | Y | Y | PASS | PASS | 0.50<=vision<0.70 and temp>50 and flame>=10 |
| 28 | 0.69 | 55.0 | 15.0 | 11.0 | Y | Y | Y | PASS | PASS | 0.50<=vision<0.70 and temp>50 and flame>=10 |
| 29 | 0.7 | 55.0 | 15.0 | 10.0 | Y | Y | Y | PASS | PASS | vision>=0.70 |
| 30 | 0.5 | 55.0 | 15.0 | 10.0 | Y | Y | Y | PASS | PASS | 0.50<=vision<0.70 and temp>50 and flame>=10 |
| 31 | 0.3 | 55.0 | 15.0 | 10.0 | Y | Y | Y | PASS | PASS | 0.30<=vision<0.50 and temp>50 and flame>=10 |
| 32 | 0.69 | 50.0 | 15.0 | 10.0 | N | N | N | PASS | PASS | 0.50<=vision<0.70 but temp/flame condition failed |
| 33 | 0.69 | 50.1 | 15.0 | 10.0 | Y | Y | Y | PASS | PASS | 0.50<=vision<0.70 and temp>50 and flame>=10 |
| 34 | 0.3 | 45.0 | 25.0 | 0.0 | Y | Y | Y | PASS | PASS | independent_trigger |
| 35 | 0.5 | 45.0 | 30.0 | 9.0 | Y | Y | Y | PASS | PASS | independent_trigger |