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

## Turnover and decay

## Neutralization and universe

## Self-correlation

## Themes that are crowded or dead
