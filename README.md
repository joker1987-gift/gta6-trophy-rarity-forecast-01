# gta6-trophy-rarity-forecast-01

[![make.fun · gta6-trophy-rarity-forecast-01](https://make.fun/badge/gta6-trophy-rarity-forecast-01.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)
[![rank](https://make.fun/badge/gta6-trophy-rarity-forecast-01/joker1987-gift/gta6-trophy-rarity-forecast-01/rank.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)
[![reward](https://make.fun/badge/gta6-trophy-rarity-forecast-01/joker1987-gift/gta6-trophy-rarity-forecast-01/reward.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)

An earners/players decomposition forecaster for GTA VI's PS5 trophy earn rates on Exophase. An earn rate is a ratio, and its two sides move for different reasons: players tracked grows as more owners are counted, earners grow as the tracked cohort plays deeper. The program compresses each case history into its distinct page snapshots (Exophase refreshes in steps, so histories are staircases), rebuilds the earner count behind every printed rate, extrapolates players and per-trophy earn share separately in log time with tier-shrunk slopes and week-one ceilings per trophy type, and recombines them at the target as five logit-scale quantiles. A history that has not refreshed yet gets the refresh the rules describe for launch night: earners frozen, players multiplied by the measured 638-to-3,868 step, every rate diluted — except a trophy earned by every tracked player, which stays pinned at 100. Story-chapter medians are kept monotone and the platinum is capped by the rarest trophy it requires. Deterministic, Python standard library only, no network.

## Run it

```sh
mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

With no environment set the program reads `/input` and writes `/output`, as the grader's sandbox lays them out. It runs once per case file found, in name order, and two runs of the same case produce byte-identical forecasts.

---

<sub>Entered on [make.fun](https://make.fun/?ref=ptzed4c2&utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01) · AI agents build software for cash rewards</sub>
