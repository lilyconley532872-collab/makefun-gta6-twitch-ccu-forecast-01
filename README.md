# GTA VI launch-day Twitch forecaster — make.fun `gta6-twitch-ccu-forecast-01`

A program that forecasts how many people watch Grand Theft Auto VI live on
Twitch in each hour of its release day (2026-11-19 UTC), as five quantiles
(5%, 25%, 50%, 75%, 95%) per hour, from the case's hour-1 print and the
case's own comparables (past big game launches' hourly curves).

Entry: `main.py` (Python 3.13, standard library only; no network, no model).
It reads every `*.in` in the input directory and writes one `<id>.out` per
case. Run locally with:

```sh
mkdir -p out && MAKEFUN_INPUT_DIR=<kit>/input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

## Method

1. **Pool** — the case's comparables whose unlock research tier is
   `"comparable"`, with a real hour-1 print (≥ 5,000 viewers) and at least
   20 of hours 2–24 present. The target's own pre-release history (tier
   `"target-history"`) is never a shape donor.
2. **Shape** — for each hour, the distribution of the log-ratio
   `ln(viewers_h / viewers_1)` across the pool. Launches differ in how much
   of the world was already unlocked in hour 1, so each ratio is adjusted
   for the launch's hour-1 size: a per-hour OLS slope of the log-ratio on
   `ln(viewers_1)`, shrunk 25% toward the pooled slope, shifts every ratio
   to the target's `ln(hour-1 print)`. (Pooled slope ≈ −0.26: bigger
   hour-1 prints rise less.)
3. **Quantiles** — median `p1 * exp(mean of adjusted log-ratios)`; spread
   their standard deviation (floored at 0.20, capped at 1.20 log units):
   `q_tau = p1 * exp(centre + z_tau * sigma)`, with the standard normal
   quantiles (−1.645, −0.674, 0, 0.674, 1.645).
4. **Fallbacks** — an hour with fewer than 3 adjusted ratios, or a pool
   smaller than 5 launches, falls back to the house baseline for that hour
   (flat at hour 1, spread `0.15 * sqrt(h − 1)`), so every case stays valid.

The shape it produces for GTA VI matches the rolling-midnight unlock: a
dip in the early morning (Europe asleep, US not yet unlocked), then a rise
through the US unlocks (05:00 and 08:00 UTC) to a peak of about 1.7× the
hour-1 print in the evening (hours 20–21 UTC), decaying toward midnight.

## Backtest (local, the grader's pinball loss on the log scale)

- The kit's 4 official practice cases (answers from SullyGnome, the source
  the kit names): **loss 0.181, typical miss 29.5%, 90% coverage 0.935**
  (house baseline on the same cases: loss 0.387, miss 82.8%, coverage 0.783).
- Leave-one-out over the 42 launches in the comparable pool (each launch
  forecast from the other 41): **loss 0.247** on the 23 GTA-like launches
  (rolling-midnight, hour-1 ≥ 5,000), 0.554 overall (house baseline:
  0.403 / 0.930 on the same sets).
- Runtime: ~0.07 s per case (cap 8 s). Output is deterministic
  (byte-identical on repeated runs) and ≤ 1,800 bytes per case (cap 65,536).

## Submission notes (for the submitter)

- Competition: `gta6-twitch-ccu-forecast-01`, $250 (top 20: $50/$35/$25/
  $10×7/$7×10), free entry, deadline **2026-11-19 01:00 UTC
  (08:00 +07 19/11)**. Max 10 submissions/day, 20 total; the last one
  before the deadline is final.
- Submission rule: **transcript bundle** (NOT strict-transcripts / sealed
  recordings). Every submission needs the AI sessions' transcripts as a
  makefun bundle or loose files, plus a run record (entries from
  17 Nov 2026 need one). The transcript gate's 10 checks apply, including
  ≥30% authored lines and the prompt being the person's own opening words.
- This repository was built **without** running the kit's `init` (no keypair
  was available to this build session), so it has no `.makefun/freshness.json`
  anchor. Submit via the **GitHub repo route** (the bounty lists a public
  GitHub repo as the deliverable): the README must carry the competition's
  three live make.fun badges and the repo's About must have a make.fun
  website + the `makefun` topic (see RULES.txt "Enter" step 4). If a source
  bundle is preferred instead, the submitter must start a fresh repo with
  `init` and replay these files; the transcript gate's `thinking_fresh`
  check then skips as a note (not a rejection).
- Suggested title: "GTA VI launch-day Twitch forecaster — comparable-launch
  log-ratio quantiles".
