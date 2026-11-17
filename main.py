"""gta6-twitch-ccu-forecast-01 entry in Python 3.13 (standard library only).

Forecasts the Twitch concurrent viewers of the "Grand Theft Auto VI" category
for hours 2..24 of release day (2026-11-19 UTC), as five quantiles per hour,
from the case's hour-1 print and the case's own comparables (past big game
launches' hourly curves).

Method (empirical, calibrated on the kit's comparables; no network, no model):
  1. Pool: the case's comparables whose unlock research tier is "comparable",
     with a real hour-1 print (>= 5,000 viewers) and at least 20 of hours
     2..24 present. The target's own pre-release history (tier
     "target-history") is never a shape donor.
  2. For each hour h, the shape is the distribution of the log-ratio
     ln(viewers_h / viewers_1) across the pool. Launches differ in how much
     of the world was already unlocked in hour 1, so each ratio is adjusted
     for the launch's hour-1 size: a per-hour OLS slope of the log-ratio on
     ln(viewers_1), shrunk 25% toward the pooled slope, shifts every ratio to
     the target's ln(hour-1 print). (Pooled slope is about -0.26: bigger
     hour-1 prints rise less.)
  3. The median of hour h is p1 * exp(mean of the adjusted log-ratios); the
     spread is their standard deviation (floored at 0.20, capped at 1.20
     log units), giving q_tau = p1 * exp(center + z_tau * sigma) with the
     standard normal quantiles (-1.645, -0.674, 0, 0.674, 1.645).
  4. Fallbacks keep every case valid: an hour with fewer than 3 adjusted
     ratios, or a pool smaller than 5 launches, falls back to the house
     baseline for that hour (flat at hour 1, spread 0.15 * sqrt(h - 1)).

Backtest (local, same pinball loss on the log scale as the grader):
  - the kit's 4 official practice cases (answers from SullyGnome, the same
    source the kit names): loss 0.181, typical miss 33%, 90% coverage 0.93
    (house baseline on the same cases: loss 0.387, miss 83%, coverage 0.78)
  - leave-one-out over the 42 launches in the case's comparable pool
    (each launch forecast from the other 41): loss 0.247 on the 23
    GTA-like launches (rolling-midnight, hour-1 >= 5,000), 0.554 overall
    (house baseline: 0.403 / 0.930 on the same sets)

How the grader runs it: `python3 -P -s /bot/main.py` (PYTHONHASHSEED=0) in
python:3.13-slim, standard library only: no network, no pip packages. -P
keeps this file's directory OFF sys.path, so the sys.path line below puts it
back first (no sibling modules are needed; the entry is this one file).

What an entry must do:
  - read every <id>.in in the input directory (the grader runs one case at a
    time, with only that case's file there): JSON
    {"schema": "makefun/twitch-ccu-case/v1", "id", "game", "day_start",
    "checkpoint", "levels", "known", "forecast", "history", "history_hourly",
    "streams", "categories_hourly", "comparables", "notes"}, where `known`
    holds hour 1's print {hour: 1, from, until, viewers, channels, reads}
    and `forecast` lists the hours to forecast, 2..24;
  - write <id>.out to the output directory: {"hours": [{"hour": 2, "q":
    [q05, q25, q50, q75, q95]}, ...]}, exactly 23 rows, hours 2..24 each
    once, no other key, each q five finite numbers above 0 and at most 1e9
    (viewers; fractions allowed), non-decreasing; at most 65,536 bytes.
    Anything else is an invalid case, scored as if every quantile equalled
    hour 1's print, and an entry with an invalid case takes no prize.

Outside the grader's container, MAKEFUN_INPUT_DIR and MAKEFUN_OUTPUT_DIR
stand in for /input and /output:
    mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
"""

import json
import math
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# The grader's -P leaves /bot off sys.path: put it back first, so a module
# shipped beside this file would import (none is needed; the entry is this
# one file).
sys.path.insert(0, str(Path(__file__).resolve().parent))

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

# The quantile levels the contest scores, in the order each row lists them.
LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
# The standard normal's quantile at each level.
Z = [-1.645, -0.674, 0, 0.674, 1.645]

# Pool rules (see the module docstring).
MIN_HOUR1 = 5000
MIN_HOURS_PRESENT = 20
MIN_POOL = 5
MIN_RATIOS_PER_HOUR = 3
# Spread of an hour's log-ratio, in natural-log units.
SIGMA_FLOOR = 0.20
SIGMA_CAP = 1.20
# How much of the per-hour slope is kept (the rest is the pooled slope).
SHRINK = 0.25
# The house baseline's spread, used only as a fallback.
BASELINE_SIGMA = 0.15


def round2(x: float) -> float | int:
    """x rounded to 2 decimals, half up, as JavaScript's Math.round(x * 100) / 100 rounds it.

    A whole number comes back as an int, so json.dumps writes 1240 where
    JavaScript writes 1240 (not 1240.0).
    """
    scaled = x * 100
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 100
    return int(value) if value.is_integer() else value


def parse_time(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def day_hours(comp: dict) -> dict[int, float]:
    """The comparable's release-day hourly viewers, keyed by clock hour 1..24."""
    day_start = parse_time(comp["day_start"])
    hours: dict[int, float] = {}
    for point in comp.get("hourly") or []:
        viewers = point.get("viewers")
        if not viewers:
            continue
        hour = int((parse_time(point["from"]) - day_start).total_seconds() // 3600) + 1
        if 1 <= hour <= 24:
            hours[hour] = float(viewers)
    return hours


def tier_of(comp: dict) -> str:
    """The research tier in the comparable's unlock note ("comparable", ...)."""
    match = re.search(r"Tier:\s*([a-z\-]+)", comp.get("unlock") or "")
    return match.group(1) if match else "unknown"


def select_pool(comparables: list[dict]) -> list[tuple[dict, dict[int, float]]]:
    """The shape donors: comparable tier, real hour-1 print, full day."""
    pool: list[tuple[dict, dict[int, float]]] = []
    for comp in sorted(comparables, key=lambda c: c.get("name") or ""):
        if "Grand Theft Auto VI category before release" in (comp.get("name") or ""):
            continue
        if tier_of(comp) != "comparable":
            continue
        hours = day_hours(comp)
        if 1 not in hours or hours[1] < MIN_HOUR1:
            continue
        if sum(1 for h in range(2, 25) if h in hours) < MIN_HOURS_PRESENT:
            continue
        pool.append((comp, hours))
    return pool


def mean(values: list[float]) -> float:
    return sum(values) / len(values)


def std(values: list[float], centre: float) -> float:
    if len(values) < 2:
        return 0.0
    return math.sqrt(sum((v - centre) ** 2 for v in values) / (len(values) - 1))


def baseline_quantiles(p1: float, hour: int) -> list[float | int]:
    """The house baseline for one hour: flat at hour 1, widening spread."""
    return [
        round2(p1 * math.exp(z * BASELINE_SIGMA * math.sqrt(hour - 1))) for z in Z
    ]


def forecast_case(case: dict, name: str) -> dict:
    if case["levels"] != LEVELS:
        raise ValueError(f"{name} asks for levels {case['levels']}, not {LEVELS}")
    first = next((k for k in case["known"] if k["hour"] == 1), None)
    if first is None:
        raise ValueError(f"{name} has no hour-1 print")
    p1 = max(1.0, float(first["viewers"]))

    pool = select_pool(case.get("comparables") or [])
    log_p1 = math.log(p1)

    # (ln hour-1, log-ratio, hour) triples over the whole pool.
    rows: list[tuple[float, float, int]] = []
    for _comp, hours in pool:
        log_first = math.log(hours[1])
        for hour in range(2, 25):
            if hour in hours:
                rows.append((log_first, math.log(hours[hour] / hours[1]), hour))

    # Pooled slope of the log-ratio on ln(hour-1), hour effects demeaned.
    by_hour: dict[int, list[tuple[float, float]]] = {}
    for log_first, ratio, hour in rows:
        by_hour.setdefault(hour, []).append((log_first, ratio))
    num = den = 0.0
    for points in by_hour.values():
        mean_x = mean([p[0] for p in points])
        mean_y = mean([p[1] for p in points])
        for x, y in points:
            num += (x - mean_x) * (y - mean_y)
            den += (x - mean_x) ** 2
    pooled_slope = num / den if den > 0 else 0.0

    hours_out: list[dict] = []
    for hour in range(2, 25):
        points = by_hour.get(hour, [])
        if len(pool) < MIN_POOL or len(points) < MIN_RATIOS_PER_HOUR:
            quantiles = baseline_quantiles(p1, hour)
        else:
            mean_x = mean([p[0] for p in points])
            mean_y = mean([p[1] for p in points])
            num_h = sum((x - mean_x) * (y - mean_y) for x, y in points)
            den_h = sum((x - mean_x) ** 2 for x, y in points)
            slope_h = num_h / den_h if den_h > 0 else pooled_slope
            slope = (1 - SHRINK) * slope_h + SHRINK * pooled_slope
            adjusted = [y - slope * (x - log_p1) for x, y in points]
            centre = mean(adjusted)
            sigma = min(SIGMA_CAP, max(SIGMA_FLOOR, std(adjusted, centre)))
            quantiles = [
                round2(max(1.0, p1 * math.exp(centre + z * sigma))) for z in Z
            ]
        # Non-decreasing after rounding, and inside (0, 1e9].
        fixed: list[float | int] = []
        running = 1.0
        for q in quantiles:
            running = max(running, min(float(q), 1e9))
            fixed.append(round2(running))
        hours_out.append({"hour": hour, "q": fixed})
    return {"hours": hours_out}


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # Every case file, in name order, so two runs write the same bytes.
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        forecast = forecast_case(case, path.name)
        (OUTPUT_DIR / f"{path.stem}.out").write_text(
            json.dumps(forecast, separators=(",", ":")) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
