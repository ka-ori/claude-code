# Lessons

One line per lesson, with the journal IDs that support it. Read before proposing; prune
lessons that later evidence contradicts.

## Signs and data

- Cash / short-term debt within subindustry (USA TOP3000 D1) has the *opposite* sign to
  the "safe firms outperform" story: group_zscore Sharpe -0.79, group_rank with
  ts_backfill Sharpe -0.83 (logged before the journal existed). Cash-rich, low-debt firms
  skew to unprofitable growth names.
- (cash_st - debt_st) / cap, group_rank by subindustry (USA TOP3000 D1, subindustry
  neutralization): train Sharpe 0.01, test Sharpe 1.02. No edge over the train period,
  so the test number is not evidence. Read train/test splits before tuning.
- Same with ts_backfill(63) and industry grouping/neutralization: train Sharpe -0.01,
  test 0.97. Dividing by cap turns it into a value signal, which likely inherits value's
  flat 2010s and recent rebound. Cash vs short-term debt is dropped as a standalone idea.
- Train window is 2019-2022; always read the yearly table, not just the aggregate.
  "Improving" fundamentals flip with the risk-on/quality cycle: liquidity vs own history
  (ts_rank 252) yearly Sharpe -2.33, -2.19, +0.52, +1.58; Piotroski-style composite
  (d-liquidity, -d-leverage, d-profitability) -0.93, -1.79, +1.12, +1.46. Aggregate ~0.
- cash_st / debt_st level, neutralized within subindustry AND size decile: -0.72, -0.01,
  -1.61, -1.03 (aggregate -0.87). Reversed, "lean on cash vs same-size peers" is the
  only version of this idea that is positive in every train year.
- Factor-momentum timing (126d trailing factor return sign) did not rescue it: timed
  ts_rank liquidity yearly -2.18, -0.34, +0.07, +1.59, test 2023 +0.51 (turnover 30% in
  2019 from flips); timed + reversed level: train 0.73 (-0.77, -0.25, +1.54, +1.33) but
  test 2023 -0.58. About 11 simulations on this one hypothesis with no stable edge:
  stop. Tutorial hint examples are not guaranteed to pass in the current IS window.

- Operating-income improvement alphas without a reversal leg all share one yearly shape:
  weak 2019, negative 2020, strong 2021-2022, negative 2023 (A0002, A0009, A0010, A0011).
  Tweaking the fundamental part does not fix it; A0001's reversal leg is what carries
  those years. Self-correlation with A0001: ratio-vs-own-history 0.88, event-gated 0.74,
  profitability blend 0.68, yoy change / EV 0.53 (lowest).

## Turnover and decay

- Fast signals (intraday reversal): Decay 7 vs 5 and hump both cut turnover but lowered
  Fitness, because Sharpe fell more (Fitness = Sharpe^1.5 * sqrt(vol / turnover)). Raising
  returns instead worked: group_rank -> group_zscore(winsorize(.., std=3)) took Fitness
  0.97 -> 1.04 at the same Sharpe (returns 8.6% -> 10.3%).
- hump scale is relative to the book: hump=0.01 froze an intraday-reversal alpha
  (turnover 0.61%, test Sharpe -1.83); 0.0002 was a usable setting. Start tiny.
- Truncation 0.01 vs 0.08 is irrelevant for rank-based TOP3000 alphas (max weight
  ~0.07% of book); it only binds for concentrated signals.

## Neutralization and universe

## Self-correlation

- Operating income / price vs its own 1-year history (A0002: ts_zscore(oi / enterprise_value, 252))
  has self-correlation 0.88 with the submitted A0001 (ts_rank(oi / cap, 252) + reversal): same bet.
  Reversal legs were not the cause (A0004 blend 0.79, A0007 >0.8). To decorrelate, change the
  structure: freeze positions between filings, or keep price out of the time comparison.
  (An earlier reading of 0.29 came from a cropped screenshot; ask for the number in text.)

## Themes that are crowded or dead
