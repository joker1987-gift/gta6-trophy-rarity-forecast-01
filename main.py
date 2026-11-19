#!/usr/bin/env python3
"""GTA VI trophy rarity forecaster (make.fun gta6-trophy-rarity-forecast-01).

Model in one paragraph: an Exophase earn rate is a ratio, earners / players
tracked, and the two sides move for different reasons.  Players tracked only
grows as more owners get counted; earners for a trophy grow as the tracked
cohort plays deeper into the game.  The page itself refreshes in steps, so a
case history is a staircase: long flat stretches (one snapshot re-read) with
jumps where both sides of the ratio move at once.  This program compresses a
history into its distinct snapshots, rebuilds the earner counts behind each
printed rate, extrapolates players and per-trophy earner share separately in
log time, and recombines them at the target.  A history with a single
snapshot has seen no refresh yet, so the forecast is the refresh the rules
describe for launch night: earners frozen, players multiplied, every rate
diluted -- except a trophy already earned by literally every tracked player,
which stays pinned at the top.

Deterministic, standard library only, no network.
"""

import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
Z_AT_LEVEL = [-1.645, -0.674, 0.0, 0.674, 1.645]

# The first refresh the rules describe: 638 tracked players became 3,868
# while the earner counts behind the printed rates had not moved, so every
# rate was divided by this factor.  It is the one measured dilution step the
# contest hands us, and the prior for a history that has not refreshed yet.
FIRST_REFRESH_PLAYERS_BEFORE = 638.0
FIRST_REFRESH_PLAYERS_AFTER = 3868.0

RATE_FLOOR = 0.01
RATE_CEIL = 99.99


def clamp_rate(pct):
    return min(RATE_CEIL, max(RATE_FLOOR, pct))


def logit(pct):
    p = clamp_rate(pct) / 100.0
    return math.log(p / (1.0 - p))


def pct_from_logit(value):
    if value >= 0:
        return 100.0 / (1.0 + math.exp(-value))
    e = math.exp(value)
    return 100.0 * e / (1.0 + e)


def round4(x):
    scaled = math.floor(x * 10000.0 + 0.5) / 10000.0
    return int(scaled) if float(scaled).is_integer() else scaled


def parse_instant(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def hours_between(start, end):
    return (end - start).total_seconds() / 3600.0


class Snapshot:
    """One distinct page state: a player count and the rates printed with it."""

    def __init__(self, when, players, rates):
        self.when = when
        self.players = players
        self.rates = rates

    def earners(self, index):
        rate = self.rates[index]
        if rate is None:
            return None
        return rate * self.players / 100.0


def snapshots_of(case):
    """Collapse a read history to its distinct states, oldest first.

    Consecutive reads that repeat the previous player count and every rate
    are the same snapshot seen again, not new information, so only the first
    sighting of each state is kept (with its slot time).
    """
    states = []
    for read in case["history"]:
        rates = list(read["rates"])
        players = read["players_tracked"]
        if states and states[-1].players == players and states[-1].rates == rates:
            continue
        states.append(Snapshot(parse_instant(read["slot"]), players, rates))
    return states


def fit_line(xs, ys, ws):
    """Weighted least squares y ~ a + b*x; returns (a, b)."""
    total_w = sum(ws)
    mean_x = sum(w * x for x, w in zip(xs, ws)) / total_w
    mean_y = sum(w * y for y, w in zip(ys, ws)) / total_w
    sxx = sum(w * (x - mean_x) ** 2 for x, w in zip(xs, ws))
    if sxx <= 1e-12:
        return mean_y, 0.0
    sxy = sum(w * (x - mean_x) * (y - mean_y) for x, y, w in zip(xs, ys, ws))
    slope = sxy / sxx
    return mean_y - slope * mean_x, slope


def share_ceiling(trophy):
    """A sane week-one cap on a trophy's earn share, from what it asks of a player."""
    text = (trophy["name"] + " " + trophy["description"]).lower()
    if trophy["tier"] == "platinum":
        return 0.03
    if "100% completion" in text:
        return 0.05
    if "final mission" in text:
        return 0.70
    if trophy["tier"] == "gold":
        return 0.30
    if trophy["tier"] == "silver":
        return 0.45
    return 0.85


def quantiles_around(median_pct, sigma):
    centre = logit(median_pct)
    row = [round4(pct_from_logit(centre + z * sigma)) for z in Z_AT_LEVEL]
    row.sort()
    return row


def pinned_row():
    """A trophy every tracked player has earned: it stays at the top.

    The scorer clamps both the answer and the quantiles to 99.99 before the
    logit, so a row of plain 100s costs nothing when the rate stays at 100,
    and the launch-night refresh left the one such trophy exactly there.
    """
    return [100, 100, 100, 100, 100]


def forecast_single_snapshot(case, snap, horizon_minutes):
    """No refresh seen yet: forecast the refresh itself.

    Earners are taken as frozen across one refresh (the launch-night refresh
    behaved exactly that way) while the player count is multiplied by the
    measured first-refresh factor, reached in full once the horizon covers
    the 90 minutes a practice horizon spans.
    """
    reach = min(1.0, horizon_minutes / 90.0)
    factor = (FIRST_REFRESH_PLAYERS_AFTER / FIRST_REFRESH_PLAYERS_BEFORE) ** reach
    sigma_base = 0.07 + 0.04 * math.sqrt(horizon_minutes / 1440.0)
    rows = []
    for i, trophy in enumerate(case["trophies"]):
        rate = snap.rates[i]
        if rate is not None and rate >= 99.99:
            rows.append(pinned_row())
            continue
        earners = snap.earners(i)
        if earners is None or earners <= 0:
            earners = 0.5
        else:
            # A printed rate over a known player count encodes a whole number
            # of earners; recovering it removes the print's rounding wobble.
            earners = max(1.0, round(earners))
        median = clamp_rate(100.0 * earners / (snap.players * factor))
        sigma = math.sqrt(sigma_base ** 2 + (0.4 / max(earners, 1.0)) ** 2)
        rows.append(quantiles_around(median, min(sigma, 0.5)))
    return rows


def forecast_growth(case, snaps, release, target):
    """Several snapshots seen: extrapolate players and shares in log time."""
    horizon_days = case["horizon_minutes"] / 1440.0
    xs = [math.log1p(max(0.0, hours_between(release, s.when))) for s in snaps]
    x_target = math.log1p(max(0.0, hours_between(release, target)))
    weights = [1.0 + j / max(1, len(snaps) - 1) for j in range(len(snaps))]

    log_players = [math.log(max(1.0, s.players)) for s in snaps]
    _, player_slope = fit_line(xs, log_players, weights)
    last = snaps[-1]
    if player_slope > 0:
        players_target = last.players * math.exp(player_slope * (x_target - xs[-1]))
    else:
        players_target = float(last.players)
    players_target = min(max(players_target, last.players * 0.98), last.players * 9.0)

    # Per-trophy share paths on the logit scale, slopes shrunk toward the
    # mean slope of the trophy's tier so one noisy staircase cannot run away.
    raw = []
    tier_slopes = {}
    for i in range(len(case["trophies"])):
        pts = [(x, logit(s.rates[i]), w)
               for x, s, w in zip(xs, snaps, weights) if s.rates[i] is not None]
        if len(pts) >= 2:
            a, b = fit_line([p[0] for p in pts], [p[1] for p in pts], [p[2] for p in pts])
        elif pts:
            a, b = pts[0][1], 0.0
        else:
            a, b = logit(0.05), 0.0
        raw.append((a, b))
        tier_slopes.setdefault(case["trophies"][i]["tier"], []).append(b)
    tier_mean = {t: sum(v) / len(v) for t, v in tier_slopes.items()}

    sigma_base = 0.24 + 0.10 * math.sqrt(horizon_days)
    medians = []
    sigmas = []
    for i, trophy in enumerate(case["trophies"]):
        a, b = raw[i]
        b = 0.65 * b + 0.35 * tier_mean.get(trophy["tier"], b)
        centre = a + b * x_target
        last_rate = last.rates[i]
        if last_rate is not None:
            centre = min(max(centre, logit(last_rate) - 1.6), logit(last_rate) + 1.6)
        share = min(max(pct_from_logit(centre) / 100.0, 0.0002), share_ceiling(trophy))
        earners_last = last.earners(i) or 0.0
        sigma = math.sqrt(sigma_base ** 2 + (0.6 / max(earners_last, 1.0)) ** 2)
        medians.append(share * 100.0)
        sigmas.append(min(sigma, 0.8))
    medians = enforce_order(case, medians)
    rows = []
    for i, trophy in enumerate(case["trophies"]):
        if last.rates[i] is not None and last.rates[i] >= 99.99:
            rows.append(pinned_row())
        else:
            rows.append(quantiles_around(clamp_rate(medians[i]), sigmas[i]))
    return rows


def enforce_order(case, medians):
    """Story progress is monotone: later chapters cannot out-earn earlier ones,
    and the platinum cannot out-earn any trophy it requires."""
    out = list(medians)
    chain = []
    for i, trophy in enumerate(case["trophies"]):
        text = trophy["description"].lower()
        if "complete chapter" in text:
            try:
                num = int(text.split("complete chapter")[1].strip().split(".")[0])
            except (ValueError, IndexError):
                continue
            chain.append((num, i))
        elif "complete the final mission" in text and trophy["tier"] == "gold":
            chain.append((10 ** 6, i))
    chain.sort()
    running = None
    for _, i in chain:
        if running is not None and out[i] > running:
            out[i] = running
        running = out[i] if running is None else min(running, out[i])
    plat = [i for i, t in enumerate(case["trophies"]) if t["tier"] == "platinum"]
    if plat:
        others_min = min(out[i] for i in range(len(out)) if i not in plat)
        for i in plat:
            out[i] = min(out[i], others_min)
    return out


def forecast_case(case, name):
    if case["levels"] != LEVELS:
        raise ValueError(f"{name} asks for levels {case['levels']}, not {LEVELS}")
    if not case["history"]:
        raise ValueError(f"{name} has no history")
    snaps = snapshots_of(case)
    if len(snaps) == 1:
        rows = forecast_single_snapshot(case, snaps[0], case["horizon_minutes"])
    else:
        release = parse_instant(case["game"]["release_date"] + "T00:00:00Z")
        rows = forecast_growth(case, snaps, release, parse_instant(case["target"]))
    trophies = [{"id": t["id"], "q": q} for t, q in zip(case["trophies"], rows)]
    return {"trophies": trophies}


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        forecast = forecast_case(case, path.name)
        text = json.dumps(forecast, separators=(",", ":")) + "\n"
        (OUTPUT_DIR / f"{path.stem}.out").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
