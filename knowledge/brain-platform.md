# WorldQuant BRAIN: what matters when writing alphas

## What an alpha is

An alpha is a Fast Expression that turns historical data into one weight per stock per
day. Positive weight = long, negative = short. BRAIN rescales the weights to the book
size and applies the settings below.

## Settings (the panel next to the editor)

| Setting | What it does | Default here |
|---|---|---|
| Region / Universe | Which stocks are tradable. TOP3000 = 3000 most liquid US names; TOP1000/TOP500 are more liquid. | USA / TOP3000 |
| Delay | 1 = signal from day *t* close trades on day *t+1*. Delay 0 trades the same day: much stricter thresholds, fragile. | 1 |
| Decay | Linear moving average of the alpha over N days. Lowers turnover, usually costs some Sharpe. | 0 |
| Neutralization | Removes market / sector / industry / subindustry exposure so returns come from relative mispricing. | SUBINDUSTRY |
| Truncation | Max weight per stock (0.08 = 8% of book). 0.01-0.10 is the sane range. | 0.08 |
| Pasteurization | Drops values for stocks outside the universe. | On |
| Unit handling / NaN handling | Unit checks on arithmetic; NaN treatment. | Verify / Off |

## Fitness

```
Fitness = Sharpe * sqrt( |Returns| / max(Turnover, 0.125) )
```

- Turnover below 12.5% earns no extra credit: once turnover is under 12.5%, more decay
  only costs Sharpe.
- `python -m alphagen fitness --sharpe S --returns R --turnover T` shows the turnover a
  given Sharpe/returns pair needs to reach Fitness 1.0.

## Default submission checks (delay 1)

| Check | Threshold |
|---|---|
| Sharpe | >= 1.25 (delay 0: 2.0) |
| Fitness | >= 1.0 (delay 0: 1.3) |
| Turnover | between 1% and 70% |
| Self-correlation | < 0.7 against your submitted alphas (or meaningfully better Sharpe than the correlated one) |
| Weight concentration, sub-universe Sharpe | must pass; shown in the check list |

The checks shown on the BRAIN website are authoritative. These are the usual defaults.

## Fast Expression rules the validator enforces

- **Lookbacks are integer constants.** `ts_mean(x, 20)`, never a variable.
- **Vector fields must be collapsed first.** Some datasets (news, sentiment, analyst
  estimates) store a list of values per stock per day. Wrap them in `vec_avg(x)`,
  `vec_sum(x)`, `vec_count(x)`, ... before any other operator.
- **Group arguments must be groups.** `group_rank(x, sector)`; to group by a numeric
  field build one: `bucket(rank(cap), range="0,1,0.1")`. `group_mean` takes three
  arguments: `group_mean(x, weight, group)`.
- **Optional parameters go by keyword.** `winsorize(x, std=4)`, `hump(x, hump=0.01)`,
  `ts_decay_exp_window(x, 10, factor=0.5)`.
- **No ternary, no `**`, no `^`.** Use `if_else(c, a, b)` and `power(x, y)` /
  `signed_power(x, y)`. `&&` and `||` are rewritten to `and(...)` / `or(...)`.
- **Multi-line alphas:** `a = expr; b = expr; final_expression`. The last statement is
  the alpha.

## Operator families

- **Time-series (`ts_*`)**: one stock's own history. Smooth (`ts_mean`,
  `ts_decay_linear`), measure change (`ts_delta`, `ts_returns`), or normalize against
  its own past (`ts_zscore`, `ts_rank`). Longer windows add lag and lower turnover.
- **Cross-sectional (`rank`, `zscore`, `winsorize`, ...)**: compare all stocks on one
  day. `rank` gives uniform weights in [0, 1] and ignores outliers. `zscore` keeps
  magnitude, so it overweights extremes.
- **Group (`group_*`)**: compare within sector/industry/subindustry. Use these for
  fundamentals, since margins and valuation ratios differ structurally across industries.
- **Event / regime**: `trade_when(trigger, alpha, exit)` only updates on trigger days
  and holds otherwise. `if_else(cond, a, b)` switches logic by regime. Both lower
  turnover and correlation.

## Common reasons alphas fail

| Symptom | Usual cause | First fix |
|---|---|---|
| High Sharpe, Fitness < 1, turnover > 30% | Daily-changing signal | Decay ladder 4 -> 6 -> 10, or `trade_when` gating |
| Turnover < 1% | Only quarterly fundamentals, plus decay | Decay 0; add a faster component |
| Sharpe ~ 1.0 | Signal is real but diluted | Try another neutralization level, a group operator, or a more liquid universe |
| Large negative Sharpe | Hypothesis sign is wrong | Flip only if the reverse story makes sense |
| Self-correlation > 0.7 | Same family as a submitted alpha | Use `knowledge/correlation-playbook.md`; changing 20 to 21 days won't help |
| Concentrated weight | A few extreme values dominate | `rank`, `winsorize(x, std=4)`, lower truncation |
