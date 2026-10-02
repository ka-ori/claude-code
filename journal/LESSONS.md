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

## Turnover and decay

## Neutralization and universe

## Self-correlation

## Themes that are crowded or dead
